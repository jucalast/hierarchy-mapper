import React, { useState } from 'react';
import {
    CheckCircle2, Loader2, ThumbsDown, Copy, RotateCcw, ThumbsUp, Building2, User2, MessageSquare, Mail, Check, ChevronDown, ChevronUp, AlertCircle, Phone, Calendar,
    Search, List, Users, Sparkles, ChevronRight, ShieldAlert, ArrowRight, ShieldCheck,
    RefreshCw, MessageCircle, GitBranch, ClipboardCheck, Zap
} from 'lucide-react';
import { Message, CompanyResult, ApprovalAction, SuggestedAction } from './ChatInterfaces';
import { AIModel } from './ModelSelector';
import { TaskList, ContactGrid, CompanyCard, ContactPill } from './modules/ContextModules';
import { WhatsAppThread, EmailThread } from './modules/CommunicationModules';
import { ActionApproval } from './modules/ActionApproval';
import { DebugPanel } from './DebugPanel';
import { getAvatarUrl, getProxiedUrl, getCompanyLogoUrl } from '../../utils/avatarUtils';
import styles from './ChatPanel.module.css';
import { TimelineEventRow, TimelineEvent } from '../prospecting/TimelineEventRow';
import { CompactEmployeeCard } from '../network-graph/CompactEmployeeCard';

import {
    ContactLogCard, DealLogCard, NoteLogCard, ActivityLogCard, EmailLogCard
} from './modules/LogModules';

// ── Mapa de ícones das ações sugeridas ──────────────────────────────────────
const ACTION_ICON_MAP: Record<string, React.ReactNode> = {
    task:     <ClipboardCheck size={13} />,
    sync:     <RefreshCw size={13} />,
    whatsapp: <MessageCircle size={13} />,
    email:    <Mail size={13} />,
    pipeline: <GitBranch size={13} />,
    default:  <Zap size={13} />,
};

// ── Chips de ações sugeridas ─────────────────────────────────────────────────
const SuggestedActionChips = ({
    actions,
    onAction,
}: {
    actions: SuggestedAction[];
    onAction: (prompt: string) => void;
}) => {
    if (!actions || actions.length === 0) return null;
    return (
        <div style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '8px',
            padding: '4px 16px 12px 16px',
        }}>
            {actions.map((action, i) => (
                <div
                    key={i}
                    role="button"
                    tabIndex={0}
                    onClick={(e) => {
                        const selection = window.getSelection();
                        if (selection && selection.toString().trim().length > 0) {
                            return;
                        }
                        onAction(action.prompt);
                    }}
                    onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            onAction(action.prompt);
                        }
                    }}
                    style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '6px',
                        padding: '6px 12px',
                        fontSize: '12px',
                        fontWeight: 500,
                        color: 'var(--chat-text-secondary)',
                        background: 'var(--chat-bg-secondary)',
                        border: 'var(--sw-border-width) solid var(--sw-border)',
                        borderRadius: '20px',
                        cursor: 'pointer',
                        transition: 'all 0.15s ease',
                        lineHeight: 1.3,
                        textAlign: 'left',
                        userSelect: 'text',
                        outline: 'none',
                    }}
                    onMouseEnter={e => {
                        const el = e.currentTarget;
                        el.style.color = 'var(--chat-text-primary)';
                        el.style.borderColor = 'rgba(94,106,210,0.6)';
                        el.style.background = 'rgba(94,106,210,0.08)';
                    }}
                    onMouseLeave={e => {
                        const el = e.currentTarget;
                        el.style.color = 'var(--chat-text-secondary)';
                        el.style.borderColor = 'var(--sw-border)';
                        el.style.background = 'var(--chat-bg-secondary)';
                    }}
                    title={action.prompt}
                >
                    <span style={{ opacity: 0.7, flexShrink: 0 }}>
                        {ACTION_ICON_MAP[action.icon || 'default']}
                    </span>
                    {action.label}
                </div>
            ))}
        </div>
    );
};

export interface RichLogEntry {
    type?: 'log' | 'thought' | 'status' | 'data_found' | 'warning' | 'stage_blocked' | 'stage_ok' | 'suggest_mapping';
    content?: string;
    entity?: string;
    data?: any;
    icon?: string;
    label?: string;
    // stage events
    message?: string;
    reason?: string;
    current_stage?: string;
    proposed_stage?: string;
    delta?: number;
    // cold lead mapping suggestion
    org_name?: string;
}

interface ChatMessageProps {
    message: Message;
    currentLogs?: (string | RichLogEntry)[];
    onApprove: (actionId: string) => void;
    onReject: (actionId: string) => void;
    onOpenWhatsApp?: (info: { name: string, id?: string }) => void;
    approvalStatuses?: Record<string, 'pending' | 'approving' | 'approved' | 'rejected'>;
    onRegenerate?: (messageId?: string) => void;
    onSuggestedAction?: (prompt: string) => void;
    model: AIModel;
}

// Mapa de ícones de status — cobre todos os valores enviados pelo backend
const STATUS_ICON_MAP: Record<string, React.ReactNode> = {
    'check': <CheckCircle2 size={12} className="text-emerald-500 shrink-0" />,
    'done_all': <CheckCircle2 size={12} className="text-emerald-500 shrink-0" />,
    'play': <CheckCircle2 size={12} className="text-emerald-500 shrink-0" />,
    'search': <Search size={12} className="text-blue-400/80 shrink-0" />,
    'list': <List size={12} className="text-blue-400/80 shrink-0" />,
    'people': <Users size={12} className="text-purple-400/80 shrink-0" />,
    'auto_awesome': <Sparkles size={12} className="text-amber-400/80 shrink-0" />,
};

// Converte activity do Pipedrive → TimelineEvent para reutilizar TimelineEventRow
const activityToEvent = (data: any): TimelineEvent => {
    const getIcon = (type: string) => {
        if (type === 'call') return <Phone size={14} />;
        if (type === 'email') return <Mail size={14} />;
        return <Calendar size={14} />;
    };
    return {
        id: data.id || Math.random(),
        type: 'activity',
        timestamp: data.due_date || '',
        title: data.subject || 'Tarefa',
        user: data.owner_name,
        contact: data.person_name,
        company: data.org_name,
        content: data.note_clean || data.note,
        done: data.done === true || data.done === 1,
        activityType: data.type,
        icon: getIcon(data.type),
    };
};

export const RichLogRenderer = ({ log, onOpenWhatsApp }: { log: string | RichLogEntry, onOpenWhatsApp?: (info: { name: string, id?: string }) => void }) => {
    if (typeof log === 'string') {
        return (
            <div className={styles.logLine}>
                <Loader2 size={12} className={styles.spinner} /> <span>{log}</span>
            </div>
        );
    }

    const { type, content, entity, data, icon, label } = log;

    switch (type) {

        // ── PENSAMENTO ───────────────────────────────────────────────────────
        case 'thought':
            return (
                <div className={styles.thoughtBlock}>
                    <div className={styles.thoughtContent}>
                        {content}
                    </div>
                </div>
            );

        // ── STATUS ──────────────────────────────────────────────────────────
        case 'status': {
            const isDone = icon === 'check' || icon === 'done_all' || icon === 'play';
            return (
                <div className={styles.logLine}>
                    {STATUS_ICON_MAP[icon ?? ''] ?? <Loader2 size={12} className={styles.spinner} />}
                    <span style={{ fontWeight: 500, color: isDone ? '#10B981' : undefined }}>{content}</span>
                </div>
            );
        }

        // ── DADOS ENCONTRADOS ────────────────────────────────────────────────
        case 'data_found':
            // Contato — MODULARIZADO: Pílula (estilo input)
            if (entity === 'contact') return <ContactPill data={data} />;

            // Email — Thread Completa (Arqueologia)
            if (entity === 'email') {
                const threadData = data.email_result || data;
                return <EmailThread data={threadData} />;
            }

            // WhatsApp — Thread Completa
            if (entity === 'whatsapp') return <WhatsAppThread data={data} onOpenWhatsApp={onOpenWhatsApp} />;

            // Negócio/Empresa — RESTAURADO: CompanyCard rico (Igual ao Drawer)
            // Só renderiza CompanyCard para entidade 'organization' para evitar duplicação
            if (entity === 'organization') return <CompanyCard data={data} />;

            // ★ Atividade → RESTAURADO: TimelineEventRow (Visualização completa de tarefa)
            if (entity === 'activity') {
                const isDone = data.done === true || data.done === 1;
                const getIcon = (type: string) => {
                    switch (type) {
                        case 'call': return <Phone size={14} />;
                        case 'meeting': return <Calendar size={14} />;
                        case 'email': return <Mail size={14} />;
                        default: return <Check size={14} />;
                    }
                };

                const event: TimelineEvent = {
                    id: data.id,
                    type: 'activity',
                    title: data.subject || 'Tarefa',
                    timestamp: data.due_date || 'Sem data',
                    done: isDone,
                    activityType: data.type,
                    icon: getIcon(data.type),
                    contact: data.person_name,
                    company: data.org_name
                };
                return (
                    <div className={styles.moduleContainer}>
                        <TimelineEventRow event={event} isLast={true} hasBackground={true} />
                    </div>
                );
            }

            // ★ Grupo de Atividades → Timeline com linhas de conexão
            if (entity === 'activities_group') {
                const activities = Array.isArray(data) ? data : [];
                const sortedActivities = activities.sort((a, b) => {
                    const dateA = new Date(a.due_date || 0).getTime();
                    const dateB = new Date(b.due_date || 0).getTime();
                    return dateA - dateB; // Ordem cronológica (mais antiga primeiro)
                });

                return (
                    <div className={styles.moduleContainer}>
                        <div className={styles.activitiesTimeline}>
                            {sortedActivities.map((activity, idx) => {
                                const isDone = activity.done === true || activity.done === 1;
                                const getIcon = (type: string) => {
                                    switch (type) {
                                        case 'call': return <Phone size={14} />;
                                        case 'meeting': return <Calendar size={14} />;
                                        case 'email': return <Mail size={14} />;
                                        default: return <Check size={14} />;
                                    }
                                };

                                const event: TimelineEvent = {
                                    id: activity.id,
                                    type: 'activity',
                                    title: activity.subject || 'Tarefa',
                                    timestamp: activity.due_date || 'Sem data',
                                    done: isDone,
                                    activityType: activity.type,
                                    icon: getIcon(activity.type),
                                    contact: activity.person_name,
                                    company: activity.org_name
                                };

                                return (
                                    <TimelineEventRow 
                                        key={activity.id} 
                                        event={event} 
                                        isLast={idx === sortedActivities.length - 1} 
                                        hasBackground={true} 
                                    />
                                );
                            })}
                        </div>
                    </div>
                );
            }

            // Nota
            if (entity === 'note') return <NoteLogCard data={data} />;

            return null;

        // ── AVISO GENÉRICO ───────────────────────────────────────────────────
        case 'warning':
            return (
                <div className={styles.warningLog}>
                    <AlertCircle size={12} className="shrink-0" />
                    <span style={{ fontWeight: 500 }}>{content || log.message}</span>
                </div>
            );

        // ── ESTÁGIO BLOQUEADO ────────────────────────────────────────────────
        case 'stage_blocked': {
            const reason = log.reason;
            const reasonLabel =
                reason === 'regression' ? 'Regressão bloqueada' :
                reason === 'skip' ? `Salto de ${log.delta} estágios bloqueado` :
                reason === 'invalid_stage' ? 'Estágio inválido' : 'Bloqueado';
            return (
                <div className={styles.stageBlocked}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <ShieldAlert size={13} style={{ color: '#ef4444', flexShrink: 0 }} />
                        <span style={{ fontSize: '11px', fontWeight: 800, color: '#ef4444', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                            {reasonLabel}
                        </span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px', color: 'var(--chat-text-secondary)' }}>
                        <span style={{ background: 'rgba(239,68,68,0.12)', color: '#fca5a5', padding: '2px 8px', borderRadius: '6px', fontWeight: 600 }}>
                            {log.current_stage}
                        </span>
                        <ArrowRight size={11} style={{ color: '#6b7280', flexShrink: 0 }} />
                        <span style={{ background: 'rgba(239,68,68,0.12)', color: '#fca5a5', padding: '2px 8px', borderRadius: '6px', fontWeight: 600, textDecoration: 'line-through', opacity: 0.7 }}>
                            {log.proposed_stage}
                        </span>
                    </div>
                    <span style={{ fontSize: '11px', color: 'var(--chat-text-muted)', fontStyle: 'italic' }}>
                        {log.message}
                    </span>
                </div>
            );
        }

        // ── ESTÁGIO AVANÇANDO (OK) ───────────────────────────────────────────
        case 'stage_ok': {
            return (
                <div className={styles.stageOk}>
                    <ShieldCheck size={13} style={{ color: '#10b981', flexShrink: 0 }} />
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px' }}>
                        <span style={{ background: 'rgba(16,185,129,0.1)', color: '#6ee7b7', padding: '2px 8px', borderRadius: '6px', fontWeight: 600 }}>
                            {log.current_stage}
                        </span>
                        <ArrowRight size={11} style={{ color: '#10b981', flexShrink: 0 }} />
                        <span style={{ background: 'rgba(16,185,129,0.1)', color: '#6ee7b7', padding: '2px 8px', borderRadius: '6px', fontWeight: 600 }}>
                            {log.proposed_stage}
                        </span>
                    </div>
                </div>
            );
        }

        // ── LEAD FRIO — SUGESTÃO DE MAPEAMENTO ──────────────────────────────
        case 'suggest_mapping': {
            const orgNameDisplay = log.org_name || 'esta empresa';
            return (
                <div className={styles.suggestMappingCard}>
                    {/* Header */}
                    <div className={styles.suggestMappingHeader}>
                        <span className={styles.suggestMappingIcon}>🧊</span>
                        <span className={styles.suggestMappingLabel}>
                            Lead Frio — Sem Histórico
                        </span>
                    </div>

                    {/* Body */}
                    <div className={styles.suggestMappingBody}>
                        {log.message || `Nenhum contato ou comunicação encontrada para ${orgNameDisplay}.`}
                    </div>

                    {/* CTA */}
                    <div className={styles.suggestMappingCTA}>
                        <Search size={13} className={styles.suggestMappingCTAIcon} />
                        <span className={styles.suggestMappingCTAText}>
                            Execute o <strong>Mapeamento de Hierarquia</strong> para {orgNameDisplay} para identificar compradores e iniciar a prospecção.
                        </span>
                        <ChevronRight size={13} className={styles.suggestMappingCTAIcon} />
                    </div>
                </div>
            );
        }

        // ── LOG DE EXECUÇÃO (default) ─────────────────────────────────────
        default: {
            const text = content || (typeof log === 'object' ? JSON.stringify(log) : '');
            const isSuccess = /^[🚀✅]/.test(text);
            const isError = /^❌/.test(text);
            const isPending = /^[📝🧪]/.test(text);
            return (
                <div className={styles.logLine} style={{
                    color: isSuccess ? '#10B981' : isError ? '#ef4444' : isPending ? '#5E6AD2' : undefined
                }}>
                    {isSuccess
                        ? <CheckCircle2 size={12} className="text-emerald-500 shrink-0" />
                        : isError
                            ? <AlertCircle size={12} className="text-red-400 shrink-0" />
                            : <Loader2 size={12} className={styles.spinner} />}
                    <span>{text}</span>
                </div>
            );
        }
    }
};

const MODEL_LOGO_MAP: Record<AIModel, string> = {
    claude: '/claude.png',
    gemini: '/gemini.png',
    groq: '/groq llama.svg',
    cerebras: '/cerebras.png',
    deepseek: '/deepseek.png',
    sambanova: '/sambanova.png',

};

const MODEL_INVERT_DARK: Partial<Record<AIModel, boolean>> = {
    groq: true,

};

const AIAsterisk = ({ model }: { model: AIModel }) => (
    <img
        src={MODEL_LOGO_MAP[model] ?? '/claude.png'}
        alt={`${model} AI`}
        width="16"
        height="16"
        className="shrink-0 object-contain"
        style={{
            filter: MODEL_INVERT_DARK[model] ? 'brightness(0) invert(1)' : 'none'
        }}
    />
);

export const ChatMessage: React.FC<ChatMessageProps> = ({
    message, currentLogs, onApprove, onReject, onOpenWhatsApp, approvalStatuses, onRegenerate, onSuggestedAction, model = 'claude'
}) => {
    const isUser = message.role === 'user';

    const renderHighlightedText = (text: string, keyPrefix: string) => {
        // Regex aprimorado: @ seguido de letras, números, espaços, hífens e acentos.
        // Para assim que encontrar pontuação comum, outra menção (@) ou fim da string.
        const parts = text.split(/(@[a-zA-Z0-9\u00C0-\u017F\s\-&]+?)(?=\s*[.,;!?(){}\[\]<>]|\s+@|$)/g);
        return parts.map((part, i) => {
            if (part.startsWith('@')) {
                return <span key={`${keyPrefix}-high-${i}`} className={styles.highlightPurple}>{part}</span>;
            }
            return part;
        });
    };

    const renderInlineMarkdown = (text: string, messageData?: any) => {
        const parts = text.split(/(\[\[(?:TASK|NEW_TASK):\d+\]\])/g);
        return parts.flatMap((part, i) => {
            if (part.startsWith('[[TASK:')) {
                const match = part.match(/\[\[TASK:(\d+)\]\]/);
                const idx = match ? parseInt(match[1]) - 1 : -1;
                const task = messageData?.past_activities?.[idx];
                return task ? [<div key={`task-${i}`} style={{ margin: '12px 0' }}><TaskList data={{ activities: [task] }} /></div>] : [];
            }
            if (part.startsWith('[[NEW_TASK:')) {
                const match = part.match(/\[\[NEW_TASK:(\d+)\]\]/);
                const idx = match ? parseInt(match[1]) - 1 : -1;
                const task = messageData?.new_activities?.[idx];
                return task ? [
                    <div key={`newtask-${i}`} style={{ margin: '12px 0' }}>
                        <div style={{ fontSize: '10px', color: task.done ? '#10B981' : '#5E6AD2', marginBottom: '4px', textTransform: 'uppercase', fontWeight: 600 }}>
                            {task.done ? 'Atividade Concluída' : 'Nova Atividade agendada'}
                        </div>
                        <TaskList data={{ activities: [task] }} />
                    </div>
                ] : [];
            }
            const tokenParts = part.split(/(\*\*.*?\*\*|`.*?`|\[.*?\]\(.*?\))/g);
            return tokenParts.flatMap((tPart, ti) => {
                if (tPart.startsWith('**') && tPart.endsWith('**')) {
                    return [<strong key={`bold-${i}-${ti}`} style={{ fontWeight: 700 }}>{tPart.slice(2, -2)}</strong>];
                }
                if (tPart.startsWith('`') && tPart.endsWith('`')) {
                    return [<span key={`code-${i}-${ti}`} style={{
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
                    }}>{tPart.slice(1, -1)}</span>];
                }
                const linkMatch = tPart.match(/^\[(.*?)\]\((.*?)\)$/);
                if (linkMatch) {
                    return [<a key={`link-${i}-${ti}`} href={linkMatch[2]} target="_blank" rel="noopener noreferrer" style={{ color: '#5E6AD2', textDecoration: 'underline' }}>{linkMatch[1]}</a>];
                }
                return renderHighlightedText(tPart, `${i}-${ti}`);
            });
        });
    };

    const renderMarkdown = (text: string, messageData?: any) => {
        if (!text) return null;
        
        // Handle code blocks first
        const blocks = text.split(/(```[\s\S]*?```)/g);
        
        return blocks.map((block, blockIdx) => {
            if (block.startsWith('```') && block.endsWith('```')) {
                const codeContent = block.slice(3, -3).replace(/^[\w-]+\n/, ''); // remove language identifier if present
                return (
                    <div key={`codeblock-${blockIdx}`} style={{ margin: '12px 0', padding: '12px', backgroundColor: 'rgba(0,0,0,0.2)', borderRadius: '6px', overflowX: 'auto', fontFamily: 'monospace', fontSize: '0.9em', border: '1px solid rgba(255,255,255,0.05)' }}>
                        <pre style={{ margin: 0 }}><code>{codeContent.trim()}</code></pre>
                    </div>
                );
            }
            
            const lines = block.split('\n');
            return lines.map((line, idx) => {
                if (line.includes('[[PAST_TASKS]]')) {
                    return (
                        <div key={`${blockIdx}-${idx}`} style={{ margin: '8px 0' }}>
                            <div style={{ fontSize: '14px', color: '#888', marginBottom: '12px', textTransform: 'uppercase', fontWeight: 800 }}>Cenário Analisado (Pipedrive)</div>
                            <TaskList data={{ activities: messageData?.past_activities }} />
                        </div>
                    );
                }
                if (line.includes('[[NEW_TASKS]]')) {
                    return (
                        <div key={`${blockIdx}-${idx}`} style={{ margin: '12px 0' }}>
                            <div style={{ fontSize: '14px', color: '#5E6AD2', marginBottom: '12px', textTransform: 'uppercase', fontWeight: 800, display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <CheckCircle2 size={16} /> Nova Atividade Gerada
                            </div>
                            <TaskList data={{ activities: messageData?.new_activities }} />
                        </div>
                    );
                }
                if (line.trim() === '---') return <hr key={`${blockIdx}-${idx}`} style={{ margin: '12px 0', border: 'none', borderTop: '1px solid rgba(255,255,255,0.1)' }} />;
                
                const trimmedLine = line.trim();
                
                if (trimmedLine.startsWith('### ')) {
                    return <h3 key={`${blockIdx}-${idx}`} style={{ fontSize: '18px', fontWeight: 'bold', marginTop: '16px', marginBottom: '8px' }}>{renderInlineMarkdown(trimmedLine.replace('### ', '').replace('🎯 ', ''), messageData)}</h3>;
                }
                if (trimmedLine.startsWith('## ')) {
                    return <h2 key={`${blockIdx}-${idx}`} style={{ fontSize: '20px', fontWeight: 'bold', marginTop: '16px', marginBottom: '8px' }}>{renderInlineMarkdown(trimmedLine.replace('## ', ''), messageData)}</h2>;
                }
                if (trimmedLine.startsWith('# ')) {
                    return <h1 key={`${blockIdx}-${idx}`} style={{ fontSize: '24px', fontWeight: 'bold', marginTop: '16px', marginBottom: '8px' }}>{renderInlineMarkdown(trimmedLine.replace('# ', ''), messageData)}</h1>;
                }
                
                // List item (number or bullet)
                const listMatch = trimmedLine.match(/^(\d+\.|[-*])\s+(.*)/);
                if (listMatch) {
                    return (
                        <div key={`${blockIdx}-${idx}`} style={{ display: 'flex', gap: '10px', marginBottom: '8px', paddingLeft: '8px' }}>
                            <span style={{ fontWeight: 'bold', minWidth: '16px', opacity: 0.8 }}>{listMatch[1].replace('*', '•').replace('-', '•')}</span>
                            <div style={{ flex: 1, lineHeight: '1.6' }}>{renderInlineMarkdown(listMatch[2], messageData)}</div>
                        </div>
                    );
                }
                
                // Empty line
                if (trimmedLine === '') {
                    return <div key={`${blockIdx}-${idx}`} style={{ height: '8px' }}></div>;
                }
                
                return <div key={`${blockIdx}-${idx}`} style={{ marginBottom: '12px', lineHeight: '1.6' }}>{renderInlineMarkdown(line, messageData)}</div>;
            });
        });
    };

    if (isUser) {
        return (
            <div className={styles.userMessageWrapper}>
                {message.selectedCompanies && message.selectedCompanies.length > 0 && (
                    <div className={styles.userCompaniesContainer}>
                        {message.selectedCompanies.map((c) => (
                            <div key={c.id} className={styles.inputCompanyPill}>
                                <div className={styles.pillIconArea}>
                                    {c.type === 'organization' ? (
                                        getCompanyLogoUrl(c) ? (
                                            <img
                                                src={getProxiedUrl(getCompanyLogoUrl(c))}
                                                alt={c.name}
                                                className={styles.pillCompanyLogo}
                                                onError={(e) => { e.currentTarget.style.display = 'none'; }}
                                            />
                                        ) : (
                                            <Building2 size={16} className="shrink-0 opacity-40" />
                                        )
                                    ) : (
                                        getAvatarUrl(c) ? (
                                            <img
                                                src={getProxiedUrl(getAvatarUrl(c))}
                                                alt={c.name}
                                                className={styles.pillCompanyLogo}
                                                style={{ borderRadius: '50%' }}
                                                onError={(e) => {
                                                    e.currentTarget.src = c.type === 'whatsapp' ? '/wppicon.png' : '/outlook.png';
                                                    e.currentTarget.style.objectFit = 'contain';
                                                }}
                                            />
                                        ) : (
                                            c.type === 'whatsapp' ?
                                                <img src="/wppicon.png" alt="W" style={{ width: 18, height: 18, objectFit: 'contain' }} /> :
                                                <img src="/outlook.png" alt="E" style={{ width: 18, height: 18, objectFit: 'contain' }} />
                                        )
                                    )}
                                </div>
                                <div className={styles.pillInfo}>
                                    <div className={styles.pillName}>{c.name}</div>
                                    <div className={styles.pillSubtext}>
                                        {c.type === 'organization' ? 'Empresa' : (c.phone || c.email || (c.type === 'whatsapp' ? 'WhatsApp' : 'E-mail'))}
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
                <div className={styles.userMessage}>{message.content}</div>
            </div>
        );
    }

    return (
        <div className={styles.assistantMessageGroup}>
            {/* Logs de Streaming e Históricos (Renderizados diretamente) */}
            {((currentLogs && currentLogs.length > 0) || (message.logs && message.logs.length > 0)) && (
                <div className="px-4 mb-4" >
                    <details className={styles.debugSection} style={{ border: 'none', background: 'transparent' }}>
                        <summary className={styles.debugSummary}>
                            <span>Agente está pensando...</span>
                            <ChevronRight size={12} className={styles.chevron} />
                        </summary>
                        
                        <div className={styles.streamingLogs} style={{ paddingLeft: '0', maxHeight: 'none', overflow: 'visible' }}>
                            {(currentLogs || message.logs || []).map((log, i) => (
                                <RichLogRenderer 
                                    key={`log-${i}`} 
                                    log={log} 
                                    onOpenWhatsApp={onOpenWhatsApp} 
                                />
                            ))}
                        </div>
                    </details>
                </div>
            )}

            <div className={styles.aiMessageWrapper}>

                <div className={styles.aiMessage}>
                    {renderMarkdown(message.content, message.data)}
                </div>
            </div>

            {/* Módulos de Interface se houver ui_module definido */}
            {message.ui_module === 'TaskList' && <TaskList data={message.data} />}
            {message.ui_module === 'ContactGrid' && <ContactGrid data={message.data} />}
            {message.ui_module === 'CompanyCard' && <CompanyCard data={message.data} />}
            {message.ui_module === 'WhatsAppThread' && <WhatsAppThread data={message.data} onOpenWhatsApp={onOpenWhatsApp} />}
            {message.ui_module === 'EmailThread' && <EmailThread data={message.data} />}

            {/* Aprovações Pendentes */}
            {message.pending_approvals && message.pending_approvals.length > 0 && (
                <div className="flex flex-col gap-3 px-4 mb-6">
                    {message.pending_approvals.map((act) => (
                        <ActionApproval
                            key={act.action_id}
                            action={act}
                            onApprove={onApprove}
                            onReject={onReject}
                            status={approvalStatuses?.[act.action_id]}
                        />
                    ))}
                </div>
            )}

            {/* Ações Sugeridas (DealStatus) */}
            {message.ui_module === 'DealStatus' && onSuggestedAction && (
                <SuggestedActionChips
                    actions={message.suggested_actions || message.data?.suggested_actions || []}
                    onAction={onSuggestedAction}
                />
            )}

            {/* Ações da Mensagem (Feedback e Utilitários) */}
            <div className={styles.messageActions}>
                <div className={styles.actionGroup}>
                    <button className={styles.actionBtn} title="Copiar resposta" onClick={() => {
                        navigator.clipboard.writeText(message.content);
                    }}>
                        <Copy size={14} />
                    </button>
                    <button className={styles.actionBtn} title="Gerar outra resposta" onClick={() => onRegenerate?.(message.id)}>
                        <RotateCcw size={14} />
                    </button>
                </div>
                <div className={styles.actionGroupDivider} />
                <div className={styles.actionGroup}>
                    <button className={styles.actionBtn} title="Resposta útil">
                        <ThumbsUp size={14} />
                    </button>
                    <button className={styles.actionBtn} title="Não foi útil">
                        <ThumbsDown size={14} />
                    </button>
                </div>
            </div>
        </div>
    );
};
