import React, { useState } from 'react';
import {
    CheckCircle2, Loader2, ThumbsDown, Copy, RotateCcw, ThumbsUp, Building2, User2, MessageSquare, Mail, Check, ChevronDown, ChevronUp, AlertCircle, Phone, Calendar,
    Search, List, Users, Sparkles
} from 'lucide-react';
import { Message, CompanyResult, ApprovalAction } from './ChatInterfaces';
import { TaskList, ContactGrid, CompanyCard } from './modules/ContextModules';
import { WhatsAppThread, EmailThread } from './modules/CommunicationModules';
import { ActionApproval } from './modules/ActionApproval';
import { DebugPanel } from './DebugPanel';
import { getAvatarUrl, getProxiedUrl, getCompanyLogoUrl } from '../../utils/avatarUtils';
import styles from '../ChatPanel.module.css';
import { TimelineEventRow, TimelineEvent } from '../TimelineEventRow';

import {
    ContactLogCard, DealLogCard, NoteLogCard
} from './modules/LogModules';

export interface RichLogEntry {
    type?: 'log' | 'thought' | 'status' | 'data_found' | 'warning';
    content?: string;
    entity?: string;
    data?: any;
    icon?: string;
    label?: string;
}

interface ChatMessageProps {
    message: Message;
    currentLogs?: (string | RichLogEntry)[];
    onApprove: (actionId: string) => void;
    onReject: (actionId: string) => void;
    onOpenWhatsApp?: (info: { name: string, id?: string }) => void;
    approvalStatuses?: Record<string, 'pending' | 'approving' | 'approved' | 'rejected'>;
}

// Mapa de ícones de status — cobre todos os valores enviados pelo backend
const STATUS_ICON_MAP: Record<string, React.ReactNode> = {
    'check':       <CheckCircle2 size={12} className="text-emerald-500 shrink-0" />,
    'done_all':    <CheckCircle2 size={12} className="text-emerald-500 shrink-0" />,
    'play':        <CheckCircle2 size={12} className="text-emerald-500 shrink-0" />,
    'search':      <Search      size={12} className="text-blue-400/80 shrink-0" />,
    'list':        <List        size={12} className="text-blue-400/80 shrink-0" />,
    'people':      <Users       size={12} className="text-purple-400/80 shrink-0" />,
    'auto_awesome':<Sparkles    size={12} className="text-amber-400/80 shrink-0" />,
};

// Converte activity do Pipedrive → TimelineEvent para reutilizar TimelineEventRow
const activityToEvent = (data: any): TimelineEvent => {
    const getIcon = (type: string) => {
        if (type === 'call')  return <Phone size={14} />;
        if (type === 'email') return <Mail  size={14} />;
        return <Calendar size={14} />;
    };
    return {
        id:           data.id || Math.random(),
        type:         'activity',
        timestamp:    data.due_date || '',
        title:        data.subject || 'Tarefa',
        user:         data.owner_name,
        contact:      data.person_name,
        company:      data.org_name,
        content:      data.note_clean || data.note,
        done:         data.done === true || data.done === 1,
        activityType: data.type,
        icon:         getIcon(data.type),
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

        // ── PENSAMENTO ──────────────────────────────────────────────────────
        case 'thought':
            return (
                <div className={styles.logLine} style={{ opacity: 1, margin: '8px 0' }}>
                    <div style={{
                        display: 'flex', alignItems: 'flex-start', gap: '10px',
                        background: 'rgba(255,255,255,0.04)', padding: '12px 14px',
                        borderRadius: '14px', border: '1px solid rgba(255,255,255,0.07)',
                        borderLeft: '3px solid rgba(251,191,36,0.35)',
                        backdropFilter: 'blur(8px)', width: '100%',
                    }}>
                        <Sparkles size={12} style={{ color: 'rgba(251,191,36,0.5)', marginTop: '2px', flexShrink: 0 }} />
                        <span style={{ fontSize: '13px', lineHeight: '1.6', color: 'rgba(255,255,255,0.75)', fontWeight: 400 }}>
                            {content}
                        </span>
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
            // Contato — pill enriquecida
            if (entity === 'contact') return <ContactLogCard data={data} label={label} />;

            // Email — card completo do CommunicationModules (já reutilizado)
            if (entity === 'email') return <EmailThread data={data} />;

            // WhatsApp — thread do CommunicationModules (já reutilizado)
            if (entity === 'whatsapp') return (
                <WhatsAppThread
                    data={{ whatsapp_result: { resultado: { messages: [data] } } }}
                    onOpenWhatsApp={onOpenWhatsApp}
                />
            );

            // Negócio
            if (entity === 'deal') return <DealLogCard data={data} />;

            // ★ Atividade → TimelineEventRow (mesmo componente do painel de agenda)
            if (entity === 'activity') return (
                <div style={{ marginLeft: '16px', marginTop: '4px', marginBottom: '4px' }}>
                    <TimelineEventRow event={activityToEvent(data)} isLast={true} hasBackground={true} />
                </div>
            );

            // Nota
            if (entity === 'note') return <NoteLogCard data={data} />;

            return null;

        // ── AVISO ────────────────────────────────────────────────────────────
        case 'warning':
            return (
                <div className={styles.logLine} style={{ color: '#fbbf24' }}>
                    <AlertCircle size={12} className="shrink-0" /> <span>{content}</span>
                </div>
            );

        // ── LOG DE EXECUÇÃO (default) ─────────────────────────────────────
        default: {
            const text = content || (typeof log === 'object' ? JSON.stringify(log) : '');
            const isSuccess = /^[🚀✅]/.test(text);
            const isError   = /^❌/.test(text);
            const isPending = /^[📝🧪]/.test(text);
            return (
                <div className={styles.logLine} style={{
                    color: isSuccess ? '#10B981' : isError ? '#ef4444' : isPending ? '#5E6AD2' : undefined
                }}>
                    {isSuccess
                        ? <CheckCircle2 size={12} className="text-emerald-500 shrink-0" />
                        : isError
                        ? <AlertCircle  size={12} className="text-red-400 shrink-0" />
                        : <Loader2 size={12} className={styles.spinner} />}
                    <span>{text}</span>
                </div>
            );
        }
    }
};

const AIAsterisk = () => (
    <img src="/gemini.png" alt="Gemini AI" width="22" height="22" className="shrink-0 mt-0.5 object-contain" />
);

const SourceIcon = () => (
    <div className="w-[18px] h-[18px] bg-[#5E6AD2] rounded-[4px] border border-white flex items-center justify-center shadow-sm relative -ml-1.5 first:ml-0">
        <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="w-2.5 h-2.5">
            <line x1="8" y1="6" x2="21" y2="6"></line>
            <line x1="8" y1="12" x2="21" y2="12"></line>
            <line x1="8" y1="18" x2="21" y2="18"></line>
            <line x1="3" y1="6" x2="3.01" y2="6"></line>
            <line x1="3" y1="12" x2="3.01" y2="12"></line>
            <line x1="3" y1="18" x2="3.01" y2="18"></line>
        </svg>
    </div>
);

const GeminiIcon = () => (
    <img src="/gemini.png" alt="Gemini" width="16" height="16" className="shrink-0 object-contain" />
);

export const ChatMessage: React.FC<ChatMessageProps> = ({ 
    message, currentLogs, onApprove, onReject, onOpenWhatsApp, approvalStatuses
}) => {
    const isUser = message.role === 'user';
    const [isLogsExpanded, setIsLogsExpanded] = useState(message.role === 'assistant' && !message.content); // Expandido por padrão se estiver rodando

    const renderHighlightedText = (text: string, keyPrefix: string) => {
        const parts = text.split(/(@\w*)/g);
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
            const boldParts = part.split(/(\*\*.*?\*\*)/g);
            return boldParts.flatMap((bPart, bi) => {
                if (bPart.startsWith('**') && bPart.endsWith('**')) {
                    return [<strong key={`bold-${i}-${bi}`} style={{ fontWeight: 700 }}>{bPart.slice(2, -2)}</strong>];
                }
                return renderHighlightedText(bPart, `${i}-${bi}`);
            });
        });
    };

    const renderMarkdown = (text: string, messageData?: any) => {
        if (!text) return null;
        const lines = text.split('\n');
        return lines.map((line, idx) => {
            if (line.includes('[[PAST_TASKS]]')) {
                return (
                    <div key={idx} style={{ margin: '8px 0' }}>
                        <div style={{ fontSize: '14px', color: '#888', marginBottom: '12px', textTransform: 'uppercase', fontWeight: 800 }}>Cenário Analisado (Pipedrive)</div>
                        <TaskList data={{ activities: messageData?.past_activities }} />
                    </div>
                );
            }
            if (line.includes('[[NEW_TASKS]]')) {
                return (
                    <div key={idx} style={{ margin: '12px 0' }}>
                        <div style={{ fontSize: '14px', color: '#5E6AD2', marginBottom: '12px', textTransform: 'uppercase', fontWeight: 800, display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <CheckCircle2 size={16} /> Nova Atividade Gerada
                        </div>
                        <TaskList data={{ activities: messageData?.new_activities }} />
                    </div>
                );
            }
            if (line.trim() === '---') return <hr key={idx} style={{ margin: '12px 0', border: 'none', borderTop: '1px solid rgba(255,255,255,0.1)' }} />;
            if (line.startsWith('### ')) {
                return <h3 key={idx} style={{ fontSize: '20px', fontWeight: 'bold', marginTop: '4px', marginBottom: '8px' }}>{renderInlineMarkdown(line.replace('### ', '').replace('🎯 ', ''), messageData)}</h3>;
            }
            return <div key={idx} style={{ marginBottom: '12px', lineHeight: '1.6' }}>{renderInlineMarkdown(line, messageData)}</div>;
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
            {/* Logs de Streaming e Históricos (Acordeon de Pensamento) - Movido para ANTES da resposta */}
            {((currentLogs && currentLogs.length > 0) || (message.logs && message.logs.length > 0)) && (
                <div className="px-4 mb-4 pl-12">
                    <div className={styles.debugCard}>
                        <button 
                            className={styles.debugHeader}
                            onClick={() => setIsLogsExpanded(!isLogsExpanded)}
                            style={{ cursor: 'pointer', background: 'none', border: 'none', width: '100%', outline: 'none' }}
                        >
                            <div className="flex items-center gap-2">
                                <span>{isLogsExpanded ? 'Esconder Pensamento' : 'Ver Pensamento da IA'}</span>
                                {message.thinkingTime && <span className={styles.thinkingTime}>({message.thinkingTime})</span>}
                            </div>
                            {isLogsExpanded ? <ChevronDown size={14} style={{ transform: isLogsExpanded ? 'none' : 'rotate(-90deg)', transition: 'transform 0.2s' }} /> : <ChevronDown size={14} style={{ transform: 'rotate(-90deg)', transition: 'transform 0.2s' }} />}
                        </button>
                        
                        {isLogsExpanded && (
                            <div className={styles.streamingLogs} style={{ paddingLeft: '24px' }}>
                                {((currentLogs && currentLogs.length > 0) ? currentLogs : (message.logs || [])).map((log, i) => (
                                    <RichLogRenderer key={`msg-log-${log.stage ?? ''}-${log.type ?? ''}-${i}`} log={log} onOpenWhatsApp={onOpenWhatsApp} />
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            )}

            <div className={styles.aiMessageWrapper}>
                <AIAsterisk />
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

            {/* Ações da Mensagem (Feedback e Utilitários) */}
            <div className={styles.messageActions}>
                <div className={styles.actionGroup}>
                    <button className={styles.actionBtn} title="Copiar resposta">
                        <Copy size={14} />
                    </button>
                    <button className={styles.actionBtn} title="Gerar outra resposta">
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
