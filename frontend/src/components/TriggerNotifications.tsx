import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
    Bell, X, Mail, MessageSquare, ArrowRight,
    Clock, TrendingUp, AlertCircle, CheckCircle2,
    ChevronDown, ExternalLink, Sparkles, Activity,
    History, Inbox, Send, RefreshCw, Layers
} from 'lucide-react';

interface TriggerEvent {
    trigger_id: string;
    channel: 'email' | 'whatsapp';
    org_id?: number;
    org_name: string;
    contact_name: string;
    contact_email?: string;
    contact_phone?: string;
    message_preview: string;
    subject?: string;
    detected_at: string;
    status: 'pending' | 'processing' | 'suggested' | 'approved' | 'dismissed';
    analysis?: string;
    sentiment?: string;
    client_intent?: string;
    urgency?: string;
    suggested_plan?: Array<{ action: string; description: string; params: Record<string, any> }>;
}

interface ActivityEvent {
    id: string;
    org_id: number;
    activity_type: string;
    status: string;
    payload: any;
    created_at: string;
    resolved_at?: string;
    org_name?: string;
}

interface TriggerNotificationsProps {
    apiBase?: string;
    onOpenChat?: (orgId: number, orgName: string, preMessage?: string) => void;
}

const SENTIMENT_CONFIG: Record<string, { color: string; label: string; icon: React.ReactNode }> = {
    positivo: { color: '#10b981', label: 'Positivo', icon: <TrendingUp size={11} /> },
    interesse: { color: '#10b981', label: 'Interesse', icon: <TrendingUp size={11} /> },
    neutro:    { color: '#6b7280', label: 'Neutro',   icon: <Clock size={11} /> },
    objeção:   { color: '#f59e0b', label: 'Objeção',  icon: <AlertCircle size={11} /> },
    negativo:  { color: '#ef4444', label: 'Negativo', icon: <AlertCircle size={11} /> },
};

const URGENCY_CONFIG: Record<string, { color: string; label: string }> = {
    alta:  { color: '#ef4444', label: '🔴 Urgente' },
    media: { color: '#f59e0b', label: '🟡 Média' },
    baixa: { color: '#6b7280', label: '⚪ Baixa' },
};

function timeSince(isoDate: string): string {
    const diff = Date.now() - new Date(isoDate).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'Agora';
    if (mins < 60) return `${mins}min atrás`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h atrás`;
    return `${Math.floor(hrs / 24)}d atrás`;
}

// ─────────────────────────────────────────────────────────────────────────────
// TRIGGER CARD
// ─────────────────────────────────────────────────────────────────────────────

const TriggerCard: React.FC<{
    trigger: TriggerEvent;
    onDismiss: (id: string) => void;
    onOpenChat?: (orgId: number, orgName: string) => void;
}> = ({ trigger, onDismiss, onOpenChat }) => {
    const [expanded, setExpanded] = useState(false);
    const sentConf = SENTIMENT_CONFIG[trigger.sentiment || 'neutro'] || SENTIMENT_CONFIG['neutro'];
    const urgConf  = URGENCY_CONFIG[trigger.urgency   || 'media']  || URGENCY_CONFIG['media'];
    const isEmail      = trigger.channel === 'email';
    const isProcessing = trigger.status  === 'processing';

    return (
        <div style={{
            background: 'var(--chat-bg-tertiary)',
            border: '1px solid var(--chat-border-weak)',
            borderRadius: 'var(--chat-radius-md)',
            overflow: 'hidden',
            transition: `all var(--chat-transition-smooth)`,
            boxShadow: 'var(--chat-shadow-sm)',
        }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, padding: 12 }}>
                {/* Channel icon */}
                <div style={{
                    width: 36, height: 36,
                    borderRadius: 10,
                    background: isEmail
                        ? 'rgba(96,165,250,0.12)'
                        : 'rgba(74,222,128,0.12)',
                    border: '1px solid var(--chat-border-weak)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                }}>
                    {isEmail
                        ? <Mail      size={16} style={{ color: '#60a5fa' }} />
                        : <MessageSquare size={16} style={{ color: '#4ade80' }} />}
                </div>

                <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--chat-text-primary)', textOverflow: 'ellipsis', whiteSpace: 'nowrap', overflow: 'hidden' }}>
                            {trigger.org_name}
                        </span>
                        <span style={{ fontSize: 10, color: 'var(--chat-text-muted)', flexShrink: 0 }}>
                            {timeSince(trigger.detected_at)}
                        </span>
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--chat-text-secondary)', marginTop: 2, fontWeight: 500 }}>
                        {trigger.contact_name}
                        {trigger.subject && <span style={{ color: 'var(--chat-text-muted)' }}> · {trigger.subject}</span>}
                    </div>
                    <div style={{
                        marginTop: 10, padding: 10,
                        background: 'var(--chat-bg-secondary)',
                        borderRadius: 'var(--chat-radius-sm)',
                        fontSize: 12, color: 'var(--chat-text-secondary)',
                        lineHeight: 1.5,
                        borderLeft: `3px solid ${isEmail ? '#3b82f6' : '#22c55e'}`,
                        fontStyle: 'italic',
                    }}>
                        {trigger.message_preview}
                    </div>
                </div>

                <button
                    onClick={() => onDismiss(trigger.trigger_id)}
                    style={{
                        background: 'transparent', border: 'none', cursor: 'pointer',
                        padding: 4, color: 'var(--chat-text-muted)', flexShrink: 0, opacity: 0.5,
                    }}
                >
                    <X size={14} />
                </button>
            </div>

            {isProcessing && (
                <div style={{ padding: '0 12px 12px', display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ display: 'flex', gap: 2 }}>
                        {[0, 1, 2].map(i => (
                            <div key={i} style={{
                                width: 3, height: 3, borderRadius: '50%',
                                background: 'var(--chat-accent-color)',
                                animation: `triggerPulse 1s infinite ${i * 0.2}s`,
                            }} />
                        ))}
                    </div>
                    <span style={{ fontSize: 11, color: 'var(--chat-accent-color)', fontWeight: 600, letterSpacing: '0.02em' }}>
                        AGENT THINKING...
                    </span>
                </div>
            )}

            {trigger.analysis && !isProcessing && (
                <div style={{ padding: '0 12px 12px' }}>
                    <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
                        <span style={{
                            display: 'flex', alignItems: 'center', gap: 5,
                            padding: '3px 10px',
                            background: `${sentConf.color}18`,
                            border: `1px solid ${sentConf.color}30`,
                            borderRadius: 999, fontSize: 10, fontWeight: 700,
                            color: sentConf.color, textTransform: 'uppercase', letterSpacing: '0.03em',
                        }}>
                            {sentConf.icon} {sentConf.label}
                        </span>
                        <span style={{
                            padding: '3px 10px',
                            background: 'var(--chat-bg-secondary)',
                            border: '1px solid var(--chat-border-weak)',
                            borderRadius: 999, fontSize: 10,
                            color: 'var(--chat-text-muted)', fontWeight: 600,
                        }}>
                            {urgConf.label}
                        </span>
                    </div>

                    <button
                        onClick={() => setExpanded(e => !e)}
                        style={{
                            display: 'flex', alignItems: 'center', gap: 6,
                            background: 'var(--chat-accent-soft)',
                            border: '1px solid var(--chat-border-weak)',
                            borderRadius: 'var(--chat-radius-sm)',
                            cursor: 'pointer', padding: '6px 10px',
                            color: 'var(--chat-accent-color)',
                            fontSize: 11, fontWeight: 600, width: '100%',
                            justifyContent: 'center',
                            transition: `all var(--chat-transition-fast)`,
                        }}
                    >
                        <Sparkles size={12} />
                        {expanded ? 'Ocultar análise estratégica' : 'Ver análise do Agente'}
                        <ChevronDown size={11} style={{
                            marginLeft: 'auto',
                            transform: expanded ? 'rotate(180deg)' : 'none',
                            transition: '0.2s',
                        }} />
                    </button>

                    {expanded && (
                        <div style={{
                            marginTop: 8, fontSize: 11,
                            color: 'var(--chat-text-secondary)',
                            lineHeight: 1.6, padding: 10,
                            background: 'var(--chat-bg-secondary)',
                            border: '1px solid var(--chat-border-weak)',
                            borderRadius: 'var(--chat-radius-sm)',
                            animation: 'triggerFadeIn 0.2s ease-out',
                        }}>
                            {trigger.analysis}
                        </div>
                    )}
                </div>
            )}

            {trigger.status === 'suggested' && trigger.org_id && onOpenChat && (
                <div style={{ padding: '0 12px 12px' }}>
                    <button
                        onClick={() => onOpenChat(trigger.org_id!, trigger.org_name)}
                        style={{
                            width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                            gap: 8, padding: '10px 12px',
                            background: 'var(--chat-accent-color)',
                            border: 'none', borderRadius: 'var(--chat-radius-md)',
                            cursor: 'pointer', fontSize: 12, fontWeight: 700, color: '#fff',
                            transition: `transform var(--chat-transition-fast), opacity var(--chat-transition-fast)`,
                            boxShadow: 'var(--chat-shadow-md)',
                        }}
                        onMouseEnter={e => (e.currentTarget.style.transform = 'translateY(-1px)')}
                        onMouseLeave={e => (e.currentTarget.style.transform = 'translateY(0)')}
                    >
                        Assumir Conversa <ArrowRight size={14} />
                    </button>
                </div>
            )}
        </div>
    );
};

// ─────────────────────────────────────────────────────────────────────────────
// ACTIVITY CARD
// ─────────────────────────────────────────────────────────────────────────────

const ActivityCard: React.FC<{
    activity: ActivityEvent;
    onOpenChat?: (orgId: number, orgName: string) => void;
}> = ({ activity, onOpenChat }) => {
    const isAwaiting = activity.status === 'awaiting_reply';
    const type    = activity.activity_type;
    const payload = activity.payload || {};

    const getIcon = () => {
        if (type.includes('email'))    return <Mail         size={15} style={{ color: '#60a5fa' }} />;
        if (type.includes('whatsapp')) return <MessageSquare size={15} style={{ color: '#4ade80' }} />;
        if (type.includes('stage'))    return <Layers        size={15} style={{ color: '#f59e0b' }} />;
        return <Activity size={15} style={{ color: 'var(--chat-text-muted)' }} />;
    };

    const getTitle = () => {
        switch (type) {
            case 'email_sent':           return 'E-mail enviado';
            case 'whatsapp_sent':        return 'WhatsApp enviado';
            case 'stage_changed':        return 'Estágio alterado';
            case 'deal_created':         return 'Negócio criado';
            case 'note_added':           return 'Nota adicionada';
            case 'email_reply_received': return 'E-mail recebido';
            case 'whatsapp_received':    return 'WhatsApp recebido';
            default: return type.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
        }
    };

    const getDescription = () => {
        if (type === 'stage_changed')   return `Fase: ${payload.from_stage} → ${payload.to_stage}`;
        if (payload.message_preview)    return payload.message_preview;
        if (payload.subject)            return payload.subject;
        return activity.org_name || 'Atividade automática';
    };

    return (
        <div
            onClick={() => activity.org_id && onOpenChat?.(activity.org_id, activity.org_name || 'Empresa')}
            style={{
                background: 'var(--chat-bg-tertiary)',
                border: '1px solid var(--chat-border-weak)',
                borderRadius: 'var(--chat-radius-md)',
                padding: 12,
                display: 'flex',
                gap: 12,
                cursor: activity.org_id ? 'pointer' : 'default',
                transition: `all var(--chat-transition-fast)`,
            }}
            onMouseEnter={e => {
                e.currentTarget.style.background    = 'var(--chat-bg-secondary)';
                e.currentTarget.style.borderColor   = 'var(--chat-border-color)';
            }}
            onMouseLeave={e => {
                e.currentTarget.style.background    = 'var(--chat-bg-tertiary)';
                e.currentTarget.style.borderColor   = 'var(--chat-border-weak)';
            }}
        >
            <div style={{
                width: 32, height: 32,
                borderRadius: 'var(--chat-radius-sm)',
                background: 'var(--chat-bg-secondary)',
                border: '1px solid var(--chat-border-weak)',
                display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
            }}>
                {getIcon()}
            </div>

            <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 4 }}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--chat-text-primary)', letterSpacing: '0.01em' }}>
                        {getTitle()}
                    </span>
                    <span style={{ fontSize: 10, color: 'var(--chat-text-muted)' }}>
                        {timeSince(activity.created_at)}
                    </span>
                </div>
                <div style={{
                    fontSize: 11, color: 'var(--chat-text-secondary)',
                    marginTop: 2, textOverflow: 'ellipsis', whiteSpace: 'nowrap', overflow: 'hidden',
                }}>
                    {getDescription()}
                </div>
                {isAwaiting && (
                    <div style={{
                        display: 'flex', alignItems: 'center', gap: 6,
                        marginTop: 8, padding: '4px 8px',
                        background: 'rgba(245,158,11,0.12)',
                        borderRadius: 'var(--chat-radius-sm)', width: 'fit-content',
                    }}>
                        <Clock size={10} style={{ color: '#f59e0b' }} />
                        <span style={{ fontSize: 10, color: '#f59e0b', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                            Aguardando resposta
                        </span>
                    </div>
                )}
            </div>
        </div>
    );
};

// ─────────────────────────────────────────────────────────────────────────────
// COMPONENTE PRINCIPAL
// ─────────────────────────────────────────────────────────────────────────────

export const TriggerNotifications: React.FC<TriggerNotificationsProps> = ({
    apiBase = '',
    onOpenChat,
}) => {
    const [triggers,          setTriggers]          = useState<TriggerEvent[]>([]);
    const [activities,        setActivities]        = useState<ActivityEvent[]>([]);
    const [activeTab,         setActiveTab]         = useState<'respostas' | 'aguardando' | 'recentes'>('respostas');
    const [open,              setOpen]              = useState(false);
    const [loadingActivities, setLoadingActivities] = useState(false);

    const panelRef = useRef<HTMLDivElement>(null);
    const esRef    = useRef<EventSource | null>(null);

    const visibleTriggers = useMemo(() =>
        triggers.filter(t => t.status !== 'dismissed' && t.status !== 'approved'),
    [triggers]);

    const awaitingReplies = useMemo(() =>
        activities.filter(a => a.status === 'awaiting_reply'),
    [activities]);

    const globalCount = visibleTriggers.length + awaitingReplies.length;

    const fetchActivities = async () => {
        setLoadingActivities(true);
        try {
            const r    = await fetch(`${apiBase}/api/v1/conversations/0/activities?limit=40`);
            const data = await r.json();
            if (Array.isArray(data)) setActivities(data);
        } catch (err) {
            console.error('Erro ao buscar atividades globais:', err);
        } finally {
            setLoadingActivities(false);
        }
    };

    useEffect(() => {
        const url = `${apiBase}/api/v1/triggers/stream/events`;
        const es  = new EventSource(url);
        esRef.current = es;

        es.onmessage = (e) => {
            try {
                const data = JSON.parse(e.data);
                if (data.type === 'trigger_update' && data.trigger) {
                    setTriggers(prev => {
                        const idx = prev.findIndex(t => t.trigger_id === data.trigger.trigger_id);
                        if (idx >= 0) {
                            const updated = [...prev];
                            updated[idx] = data.trigger;
                            return updated;
                        }
                        return [data.trigger, ...prev];
                    });
                    fetchActivities();
                }
            } catch { /* ignore parse errors */ }
        };

        es.onerror = () => {
            es.close();
            setTimeout(() => { if (esRef.current === es) esRef.current = null; }, 10000);
        };

        fetch(`${apiBase}/api/v1/triggers`)
            .then(r => r.json())
            .then(data => { if (data.triggers?.length) setTriggers(data.triggers); })
            .catch(() => {});

        fetchActivities();

        return () => { es.close(); esRef.current = null; };
    }, [apiBase]);

    useEffect(() => {
        if (open) fetchActivities();
    }, [open]);

    useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (open && panelRef.current && !panelRef.current.contains(e.target as Node))
                setOpen(false);
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, [open]);

    const handleDismiss = async (triggerId: string) => {
        try {
            await fetch(`${apiBase}/api/v1/triggers/${triggerId}/dismiss`, { method: 'POST' });
        } catch { /* silently fail */ }
        setTriggers(prev =>
            prev.map(t => t.trigger_id === triggerId ? { ...t, status: 'dismissed' as const } : t)
        );
    };

    const handleOpenChat = (orgId: number, orgName: string) => {
        setOpen(false);
        if (onOpenChat) onOpenChat(orgId, orgName);
    };

    const TABS = [
        { id: 'respostas',  label: 'Respostas',  icon: <Inbox    size={13} />, count: visibleTriggers.length },
        { id: 'aguardando', label: 'Aguardando', icon: <Clock    size={13} />, count: awaitingReplies.length },
        { id: 'recentes',   label: 'Feed Total', icon: <Activity size={13} /> },
    ] as const;

    return (
        <div style={{ position: 'relative' }} ref={panelRef}>
            {/* Bell button */}
            <button
                onClick={() => setOpen(o => !o)}
                style={{
                    position: 'relative',
                    background: open
                        ? 'var(--chat-accent-soft)'
                        : 'transparent',
                    border: open
                        ? '1px solid var(--chat-border-color)'
                        : '1px solid transparent',
                    borderRadius: 'var(--chat-radius-sm)',
                    padding: 7,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    color: globalCount > 0
                        ? 'var(--chat-accent-color)'
                        : 'var(--chat-text-muted)',
                    transition: `all var(--chat-transition-fast)`,
                    outline: 'none',
                }}
                className="notif-bell-btn"
            >
                <Bell size={18} style={{
                    animation: visibleTriggers.length > 0 ? 'triggerPulse 2s infinite' : 'none',
                }} />
                {globalCount > 0 && (
                    <span style={{
                        position: 'absolute', top: -4, right: -4,
                        background: visibleTriggers.length > 0 ? '#ef4444' : '#f59e0b',
                        color: '#fff', fontSize: 10, fontWeight: 800,
                        borderRadius: 999, minWidth: 18, height: 18,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        padding: '0 4px',
                        border: '2px solid var(--chat-bg-primary)',
                    }}>
                        {globalCount > 9 ? '9+' : globalCount}
                    </span>
                )}
            </button>

            {open && (
                <div style={{
                    position: 'absolute',
                    top: 'calc(100% + 12px)',
                    right: 0,
                    width: 400,
                    maxHeight: 600,
                    overflowY: 'hidden',
                    background: 'var(--chat-bg-primary)',
                    backdropFilter: 'blur(40px)',
                    border: '1px solid var(--chat-border-color)',
                    borderRadius: 'var(--chat-radius-lg)',
                    boxShadow: 'var(--chat-shadow-lg)',
                    zIndex: 9999,
                    display: 'flex',
                    flexDirection: 'column',
                    animation: 'notifSlideIn 0.25s cubic-bezier(0.16, 1, 0.3, 1)',
                }}>
                    {/* Tabs */}
                    <div style={{
                        display: 'flex',
                        padding: '12px 12px 0',
                        borderBottom: '1px solid var(--chat-border-weak)',
                        background: 'var(--chat-bg-tertiary)',
                        borderRadius: 'var(--chat-radius-lg) var(--chat-radius-lg) 0 0',
                    }}>
                        {TABS.map(tab => {
                            const isActive = activeTab === tab.id;
                            return (
                                <button
                                    key={tab.id}
                                    onClick={() => setActiveTab(tab.id)}
                                    style={{
                                        flex: 1,
                                        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                                        padding: '10px 8px 11px',
                                        background: 'transparent',
                                        border: 'none',
                                        borderBottom: isActive
                                            ? '2px solid var(--chat-accent-color)'
                                            : '2px solid transparent',
                                        color: isActive
                                            ? 'var(--chat-accent-color)'
                                            : 'var(--chat-text-muted)',
                                        fontSize: 12,
                                        fontWeight: 700,
                                        cursor: 'pointer',
                                        transition: `all var(--chat-transition-fast)`,
                                        opacity: isActive ? 1 : 0.65,
                                        outline: 'none',
                                    }}
                                    className="notif-tab-btn"
                                >
                                    {tab.icon}
                                    {tab.label}
                                    {'count' in tab && tab.count !== undefined && tab.count > 0 && (
                                        <span style={{
                                            background: tab.id === 'respostas' ? '#ef4444' : '#f59e0b',
                                            fontSize: 10, padding: '1px 6px',
                                            borderRadius: 999, color: '#fff',
                                            fontWeight: 800,
                                        }}>
                                            {tab.count}
                                        </span>
                                    )}
                                </button>
                            );
                        })}
                    </div>

                    {/* Content */}
                    <div style={{
                        flex: 1, overflowY: 'auto',
                        padding: 12,
                        display: 'flex', flexDirection: 'column', gap: 10,
                        maxHeight: 460,
                    }}>
                        {activeTab === 'respostas' && (
                            visibleTriggers.length === 0
                                ? <EmptyState icon={<Inbox size={36} />} title="Tudo em dia!" subtitle="Nenhuma nova resposta detectada." />
                                : visibleTriggers.map(t =>
                                    <TriggerCard key={t.trigger_id} trigger={t} onDismiss={handleDismiss} onOpenChat={handleOpenChat} />
                                )
                        )}

                        {activeTab === 'aguardando' && (
                            awaitingReplies.length === 0
                                ? <EmptyState icon={<Clock size={36} />} title="Sem pendências" subtitle="Ninguém está no vácuo no momento." />
                                : awaitingReplies.map(a =>
                                    <ActivityCard key={a.id} activity={a} onOpenChat={handleOpenChat} />
                                )
                        )}

                        {activeTab === 'recentes' && (
                            <>
                                {loadingActivities && activities.length === 0 ? (
                                    <div style={{ padding: 40, textAlign: 'center' }}>
                                        <RefreshCw size={24} style={{ opacity: 0.3, margin: '0 auto', color: 'var(--chat-accent-color)', display: 'block', animation: 'spin 1s linear infinite' }} />
                                    </div>
                                ) : activities.length === 0 ? (
                                    <EmptyState icon={<Activity size={36} />} title="Feed vazio" subtitle="Nenhuma atividade registrada ainda." />
                                ) : (
                                    activities.map(a =>
                                        <ActivityCard key={a.id} activity={a} onOpenChat={handleOpenChat} />
                                    )
                                )}
                            </>
                        )}
                    </div>

                    {/* Footer */}
                    <div style={{
                        padding: '10px 16px',
                        borderTop: '1px solid var(--chat-border-weak)',
                        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                        background: 'var(--chat-bg-tertiary)',
                        borderRadius: '0 0 var(--chat-radius-lg) var(--chat-radius-lg)',
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <div style={{
                                width: 6, height: 6, borderRadius: '50%',
                                background: '#10b981',
                                boxShadow: '0 0 6px #10b981',
                            }} />
                            <span style={{ fontSize: 10, color: 'var(--chat-text-muted)', fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase' }}>
                                System Live
                            </span>
                        </div>
                        <button
                            onClick={fetchActivities}
                            style={{
                                background: 'var(--chat-bg-secondary)',
                                border: '1px solid var(--chat-border-weak)',
                                cursor: 'pointer',
                                color: 'var(--chat-text-secondary)',
                                display: 'flex', alignItems: 'center', gap: 5,
                                fontSize: 11, fontWeight: 700,
                                padding: '5px 10px',
                                borderRadius: 'var(--chat-radius-sm)',
                                transition: `all var(--chat-transition-fast)`,
                                outline: 'none',
                            }}
                            className="notif-refresh-btn"
                        >
                            <RefreshCw size={11} style={{ animation: loadingActivities ? 'spin 1s linear infinite' : 'none' }} />
                            Atualizar
                        </button>
                    </div>
                </div>
            )}

            <style>{`
                .notif-bell-btn:hover {
                    background: var(--chat-bg-secondary) !important;
                    border-color: var(--chat-border-weak) !important;
                    color: var(--chat-text-primary) !important;
                }
                .notif-tab-btn:hover {
                    opacity: 1 !important;
                    color: var(--chat-text-primary) !important;
                }
                .notif-refresh-btn:hover {
                    background: var(--chat-bg-primary) !important;
                    border-color: var(--chat-border-color) !important;
                }
                @keyframes triggerPulse {
                    0%, 100% { opacity: 1; }
                    50%       { opacity: 0.4; }
                }
                @keyframes triggerFadeIn {
                    from { opacity: 0; transform: translateY(-4px); }
                    to   { opacity: 1; transform: translateY(0); }
                }
                @keyframes notifSlideIn {
                    from { opacity: 0; transform: translateY(-6px) scale(0.98); }
                    to   { opacity: 1; transform: translateY(0)   scale(1); }
                }
                @keyframes spin {
                    from { transform: rotate(0deg); }
                    to   { transform: rotate(360deg); }
                }
            `}</style>
        </div>
    );
};

// ─── Empty state helper ───────────────────────────────────────────────────────
const EmptyState: React.FC<{ icon: React.ReactNode; title: string; subtitle: string }> = ({ icon, title, subtitle }) => (
    <div style={{
        padding: '52px 20px',
        textAlign: 'center',
        color: 'var(--chat-text-muted)',
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8,
    }}>
        <div style={{ opacity: 0.18 }}>{icon}</div>
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--chat-text-secondary)' }}>{title}</span>
        <span style={{ fontSize: 11, opacity: 0.7 }}>{subtitle}</span>
    </div>
);

export default TriggerNotifications;
