import React from 'react';
import {
    User2, Building2, MessageSquare, ArrowUpRight, ArrowDownLeft, ArrowRight, Phone, Mail, Calendar, CheckCircle2, Clock
} from 'lucide-react';
import styles from '../../ChatPanel.module.css';

// ─────────────────────────────────────────────────────────────────────────────
// ContactLogCard
// Pill de contato usada no painel de pensamento.
// Alinha visualmente com as pills de empresa do input de chat.
// ─────────────────────────────────────────────────────────────────────────────
export const ContactLogCard = ({ data, label }: { data: any; label?: string }) => {
    const isUnmapped = data.is_unmapped || data.source?.includes("Não vinculado");

    return (
        <div className={styles.logCard} style={{
            filter: isUnmapped ? 'grayscale(80%)' : 'none',
            opacity: isUnmapped ? 0.65 : 1,
            maxWidth: '340px',
        }}>
            {/* Avatar / ícone */}
            <div style={{
                padding: '6px', borderRadius: '8px',
                background: isUnmapped ? 'rgba(100,100,100,0.15)' : 'rgba(139,92,246,0.15)',
                flexShrink: 0,
            }}>
                <User2 size={13} style={{ color: isUnmapped ? '#6b7280' : '#a78bfa' }} />
            </div>

            {/* Nome + fonte + email */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1px', minWidth: 0 }}>
                <span style={{
                    fontSize: '12px', fontWeight: 600,
                    color: isUnmapped ? '#6b7280' : 'var(--chat-text-primary)',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>{data.name}</span>
                {data.email && (
                    <span style={{ fontSize: '10px', color: 'var(--chat-accent-color)', fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', opacity: 0.8 }}>
                        {data.email}
                    </span>
                )}
                {data.source && !data.email && (
                    <span style={{ fontSize: '9px', color: 'var(--chat-text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                        {data.source}
                    </span>
                )}
            </div>

            {/* Canais disponíveis */}
            {data.channels && data.channels.length > 0 && (
                <div style={{ display: 'flex', gap: '4px', marginLeft: '4px', borderLeft: '1px solid var(--chat-border-weak)', paddingLeft: '8px', flexShrink: 0 }}>
                    {data.channels.includes('WhatsApp') && (
                        <img src="/wppicon.png" width="13" height="13" alt="WhatsApp"
                            style={{ filter: isUnmapped ? 'grayscale(1) opacity(0.5)' : 'none', transition: 'filter 0.2s' }} />
                    )}
                    {data.channels.includes('Email') && (
                        <img src="/outlook.png" width="13" height="13" alt="Email"
                            style={{ filter: isUnmapped ? 'grayscale(1) opacity(0.5)' : 'none', transition: 'filter 0.2s' }} />
                    )}
                </div>
            )}

            {/* Badge de prioridade */}
            {label && (
                <span style={{
                    fontSize: '9px', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em',
                    padding: '2px 6px', borderRadius: '999px',
                    background: 'var(--chat-accent-soft)', color: 'var(--chat-accent-color)',
                    border: '1px solid var(--chat-accent-soft)', flexShrink: 0,
                }}>{label}</span>
            )}
        </div>
    );
};

// ─────────────────────────────────────────────────────────────────────────────
// DealLogCard
// Card de negócio com indicador de estágio e valor.
// ─────────────────────────────────────────────────────────────────────────────
export const DealLogCard = ({ data }: { data: any }) => {
    const hasValue = data.value && data.value > 0;
    const isOpen = data.status === 'open';
    const stageName = data.stage_name || 'Sem etapa';

    return (
        <div className={styles.logCard} style={{ maxWidth: '340px' }}>
            {/* Ícone */}
            <div style={{ padding: '8px', borderRadius: '10px', background: 'var(--chat-bg-tertiary)', flexShrink: 0 }}>
                <Building2 size={15} style={{ color: 'var(--chat-text-muted)' }} />
            </div>

            {/* Info */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '3px', minWidth: 0 }}>
                {/* Título + etapa */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span style={{
                        fontSize: '12px', fontWeight: 700, color: 'var(--chat-text-primary)',
                        textTransform: 'uppercase', letterSpacing: '0.03em',
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>{data.title || data.org_name}</span>
                    <span style={{
                        fontSize: '10px', fontWeight: 700, padding: '2px 7px', borderRadius: '6px',
                        background: 'var(--chat-accent-soft)', color: 'var(--chat-accent-color)',
                        border: '1px solid var(--chat-accent-soft)',
                        flexShrink: 0,
                    }}>{stageName}</span>
                </div>

                {/* Valor + status */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span style={{ fontSize: '11px', color: 'var(--chat-text-secondary)', fontWeight: 500 }}>
                        {hasValue ? data.formatted_value : 'Sem valor definido'}
                    </span>
                    <span style={{ width: '3px', height: '3px', borderRadius: '50%', background: 'var(--chat-border-weak)', flexShrink: 0 }} />
                    <span style={{
                        fontSize: '10px', fontWeight: 600,
                        color: isOpen ? '#10B981' : 'var(--chat-text-muted)',
                    }}>{isOpen ? 'Em aberto' : data.status}</span>
                </div>
            </div>
        </div>
    );
};

// ─────────────────────────────────────────────────────────────────────────────
// NoteLogCard
// Card de nota interna com destaque âmbar.
// ─────────────────────────────────────────────────────────────────────────────
export const NoteLogCard = ({ data }: { data: any }) => (
    <div className={styles.logCard} style={{
        flexDirection: 'column', gap: '6px',
        background: 'rgba(245,158,11,0.05)',
        borderLeft: '3px solid rgba(245,158,11,0.4)',
        maxWidth: '320px',
        alignItems: 'flex-start'
    }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <MessageSquare size={11} style={{ color: 'rgba(251,191,36,0.7)' }} />
            <span style={{ fontSize: '9px', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'rgba(251,191,36,0.7)' }}>
                Nota Interna
            </span>
        </div>
        <div style={{
            fontSize: '11px', color: 'var(--chat-text-secondary)', lineHeight: '1.5',
            display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical',
            overflow: 'hidden', fontStyle: 'italic',
        }}>
            {data.content}
        </div>
    </div>
);

// ─────────────────────────────────────────────────────────────────────────────
// ActivityLogCard
// Pill de atividade/tarefa usada no painel de pensamento.
// ─────────────────────────────────────────────────────────────────────────────
export const ActivityLogCard = ({ data }: { data: any }) => {
    const isDone = data.done === true || data.done === 1;
    
    const getIcon = (type: string) => {
        switch (type) {
            case 'call': return <Phone size={13} />;
            case 'meeting': return <Calendar size={13} />;
            case 'email': return <Mail size={13} />;
            default: return <CheckCircle2 size={13} />;
        }
    };

    return (
        <div className={styles.logCard} style={{ maxWidth: '340px' }}>
            <div style={{
                padding: '6px', borderRadius: '8px',
                background: isDone ? 'rgba(16,185,129,0.15)' : 'var(--chat-accent-soft)',
                flexShrink: 0,
            }}>
                <span style={{ color: isDone ? '#10B981' : 'var(--chat-accent-color)' }}>
                    {getIcon(data.type)}
                </span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1px', minWidth: 0 }}>
                <span style={{
                    fontSize: '12px', fontWeight: 600,
                    color: 'var(--chat-text-primary)',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>{data.subject || 'Tarefa'}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <Clock size={10} style={{ color: 'var(--chat-text-muted)' }} />
                    <span style={{ fontSize: '10px', color: 'var(--chat-text-muted)', fontWeight: 500 }}>
                        {data.due_date || 'Sem data'}
                    </span>
                    {data.person_name && (
                        <>
                            <span style={{ fontSize: '10px', color: 'var(--chat-border-weak)' }}>•</span>
                            <span style={{ fontSize: '10px', color: 'var(--chat-accent-color)', fontWeight: 600, opacity: 0.8 }}>{data.person_name}</span>
                        </>
                    )}
                </div>
            </div>

            {isDone && (
                <div style={{ 
                    marginLeft: '4px', padding: '2px 6px', borderRadius: '6px', 
                    background: 'rgba(16,185,129,0.1)', color: '#10B981', 
                    fontSize: '9px', fontWeight: 800, textTransform: 'uppercase' 
                }}>
                    Ok
                </div>
            )}
        </div>
    );
};

// ─────────────────────────────────────────────────────────────────────────────
// EmailLogCard
// Pill de email usada no painel de pensamento.
// ─────────────────────────────────────────────────────────────────────────────
export const EmailLogCard = ({ data }: { data: any }) => {
    const emailResult = data?.email_result || data || {};
    const subject = emailResult.subject || "Sem Assunto";
    const contact = emailResult.contact || emailResult.resolved_contact || { name: emailResult.to, email: emailResult.to };

    return (
        <div className={styles.logCard} style={{ maxWidth: '340px' }}>
            <div style={{
                padding: '4px', borderRadius: '8px',
                background: 'var(--chat-bg-tertiary)',
                flexShrink: 0,
            }}>
                <img src="/outlook.png" width="16" height="16" alt="Email" style={{ objectFit: 'contain' }} />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1px', minWidth: 0 }}>
                <span style={{
                    fontSize: '12px', fontWeight: 600,
                    color: 'var(--chat-text-primary)',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>{subject}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span style={{ fontSize: '10px', color: 'var(--chat-accent-color)', fontWeight: 600, opacity: 0.8 }}>{contact.name || contact.email}</span>
                    {emailResult.date && (
                        <>
                            <span style={{ fontSize: '10px', color: 'var(--chat-border-weak)' }}>•</span>
                            <span style={{ fontSize: '10px', color: 'var(--chat-text-muted)' }}>{emailResult.date}</span>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
};
