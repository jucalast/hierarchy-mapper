import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
    Bell, X, Mail, MessageSquare, ArrowRight,
    Clock, TrendingUp, AlertCircle, CheckCircle2,
    ChevronDown, ExternalLink, Sparkles, Activity,
    History, Inbox, Send, RefreshCw, Layers
} from 'lucide-react';
import styles from './TriggerNotifications.module.css';

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
    neutro: { color: '#6b7280', label: 'Neutro', icon: <Clock size={11} /> },
    objeção: { color: '#f59e0b', label: 'Objeção', icon: <AlertCircle size={11} /> },
    negativo: { color: '#ef4444', label: 'Negativo', icon: <AlertCircle size={11} /> },
};

const URGENCY_CONFIG: Record<string, { color: string; label: string }> = {
    alta: { color: '#ef4444', label: '🔴 Urgente' },
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
    const urgConf = URGENCY_CONFIG[trigger.urgency || 'media'] || URGENCY_CONFIG['media'];
    const isEmail = trigger.channel === 'email';
    const isProcessing = trigger.status === 'processing';

    return (
        <div className={styles.card}>
            <div className={styles.cardHeader}>
                <div className={styles.iconBox}>
                    {isEmail
                        ? <Mail size={16} style={{ color: '#60a5fa' }} />
                        : <MessageSquare size={16} style={{ color: '#4ade80' }} />}
                </div>

                <div className={styles.cardBody}>
                    <div className={styles.cardTitleRow}>
                        <span className={styles.orgName}>
                            {trigger.org_name}
                        </span>
                        <span className={styles.time}>
                            {timeSince(trigger.detected_at)}
                        </span>
                    </div>
                    <div className={styles.contactInfo}>
                        {trigger.contact_name}
                        {trigger.subject && <span style={{ opacity: 0.5 }}> · {trigger.subject}</span>}
                    </div>
                    <div className={styles.messagePreview} style={{ borderLeftColor: isEmail ? '#3b82f6' : '#22c55e' }}>
                        {trigger.message_preview}
                    </div>
                </div>

                <button onClick={() => onDismiss(trigger.trigger_id)} className={styles.dismissBtn}>
                    <X size={14} />
                </button>
            </div>

            {isProcessing && (
                <div style={{ padding: '0 12px 12px', display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ display: 'flex', gap: 2 }}>
                        {[0, 1, 2].map(i => (
                            <div key={i} style={{
                                width: 3, height: 3, borderRadius: '50%',
                                background: 'var(--sw-accent)',
                            }} />
                        ))}
                    </div>
                    <span style={{ fontSize: 11, color: 'var(--sw-accent)', fontWeight: 600, letterSpacing: '0.02em' }}>
                        AGENT THINKING...
                    </span>
                </div>
            )}

            {trigger.analysis && !isProcessing && (
                <div className={styles.analysisSection}>
                    <div className={styles.tagRow}>
                        <span className={styles.tag} style={{ color: sentConf.color }}>
                            {sentConf.icon} {sentConf.label}
                        </span>
                        <span className={styles.tag} style={{ color: 'rgba(255,255,255,0.6)' }}>
                            {urgConf.label}
                        </span>
                    </div>

                    <button onClick={() => setExpanded(e => !e)} className={styles.expandBtn}>
                        <Sparkles size={12} />
                        {expanded ? 'Ocultar análise estratégica' : 'Ver análise do Agente'}
                        <ChevronDown size={11} style={{ marginLeft: 'auto', transform: expanded ? 'rotate(180deg)' : 'none', transition: '0.2s' }} />
                    </button>

                    {expanded && (
                        <div className={styles.analysisText}>
                            {trigger.analysis}
                        </div>
                    )}
                </div>
            )}

            {trigger.status === 'suggested' && trigger.org_id && onOpenChat && (
                <div style={{ padding: '0 12px 12px' }}>
                    <button onClick={() => onOpenChat(trigger.org_id!, trigger.org_name)} className={styles.actionBtn}>
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
    const type = activity.activity_type;
    const payload = activity.payload || {};

    const getIcon = () => {
        if (type.includes('email')) return <Mail size={15} style={{ color: '#60a5fa' }} />;
        if (type.includes('whatsapp')) return <MessageSquare size={15} style={{ color: '#4ade80' }} />;
        if (type.includes('stage')) return <Layers size={15} style={{ color: '#f59e0b' }} />;
        return <Activity size={15} style={{ color: 'rgba(255,255,255,0.4)' }} />;
    };

    const getTitle = () => {
        switch (type) {
            case 'email_sent': return 'E-mail enviado';
            case 'whatsapp_sent': return 'WhatsApp enviado';
            case 'stage_changed': return 'Estágio alterado';
            case 'deal_created': return 'Negócio criado';
            case 'note_added': return 'Nota adicionada';
            case 'email_reply_received': return 'E-mail recebido';
            case 'whatsapp_received': return 'WhatsApp recebido';
            default: return type.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
        }
    };

    const getDescription = () => {
        if (type === 'stage_changed') return `Fase: ${payload.from_stage} → ${payload.to_stage}`;
        if (payload.message_preview) return payload.message_preview;
        if (payload.subject) return payload.subject;
        return activity.org_name || 'Atividade automática';
    };

    return (
        <div
            onClick={() => activity.org_id && onOpenChat?.(activity.org_id, activity.org_name || 'Empresa')}
            className={styles.card}
            style={{ padding: 12, display: 'flex', gap: 12, cursor: activity.org_id ? 'pointer' : 'default' }}
        >
            <div className={styles.iconBox} style={{ width: 32, height: 32 }}>
                {getIcon()}
            </div>

            <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 4 }}>
                    <span className={styles.orgName} style={{ fontSize: 12 }}>
                        {getTitle()}
                    </span>
                    <span className={styles.time}>
                        {timeSince(activity.created_at)}
                    </span>
                </div>
                <div className={styles.contactInfo} style={{ marginTop: 2 }}>
                    {getDescription()}
                </div>
                {isAwaiting && (
                    <div style={{
                        display: 'flex', alignItems: 'center', gap: 6,
                        marginTop: 8, padding: '4px 8px',
                        background: 'rgba(245,158,11,0.12)',
                        borderRadius: 'var(--radius-sm)', width: 'fit-content',
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
    const [triggers, setTriggers] = useState<TriggerEvent[]>([]);
    const [activities, setActivities] = useState<ActivityEvent[]>([]);
    const [activeTab, setActiveTab] = useState<'respostas' | 'aguardando' | 'recentes'>('respostas');
    const [open, setOpen] = useState(false);
    const [loadingActivities, setLoadingActivities] = useState(false);

    const panelRef = useRef<HTMLDivElement>(null);
    const esRef = useRef<EventSource | null>(null);

    const visibleTriggers = useMemo(() =>
        triggers.filter(t => t.status !== 'dismissed' && t.status !== 'approved'),
        [triggers]);

    const awaitingReplies = useMemo(() =>
        activities.filter(a => a.status === 'awaiting_reply'),
        [activities]);

    const globalCount = visibleTriggers.length + awaitingReplies.length;

    const fetchActivities = async () => {
        if (loadingActivities) return;
        setLoadingActivities(true);
        try {
            const { apiGet } = await import('@/services/config');
            const data = await apiGet(`/conversations/0/activities?limit=40`);
            if (Array.isArray(data)) setActivities(data);
        } catch (err) {
            // Silencioso
        } finally {
            setLoadingActivities(false);
        }
    };

    useEffect(() => {
        const url = `${apiBase}/api/v1/triggers/stream/events`;
        const es = new EventSource(url);
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
            } catch { /* ignore */ }
        };

        es.onerror = () => {
            es.close();
            setTimeout(() => { if (esRef.current === es) esRef.current = null; }, 10000);
        };

        import('@/services/config').then(({ apiGet }) => {
            apiGet('/triggers')
                .then(data => { if (data.triggers?.length) setTriggers(data.triggers); })
                .catch(() => { });
        });

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
            const { apiPost } = await import('@/services/config');
            await apiPost(`/triggers/${triggerId}/dismiss`);
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
        { id: 'respostas', label: 'Respostas', icon: <Inbox size={13} />, count: visibleTriggers.length },
        { id: 'aguardando', label: 'Aguardando', icon: <Clock size={13} />, count: awaitingReplies.length },
        { id: 'recentes', label: 'Feed Total', icon: <Activity size={13} /> },
    ] as const;

    return (
        <div style={{ position: 'relative', zIndex: 10001 }} ref={panelRef}>
            <button
                onClick={() => setOpen(o => !o)}
                className={`${styles.bellBtn} ${open ? styles.bellBtnActive : ''}`}
            >
                <Bell size={18} />
                {globalCount > 0 && (
                    <span className={styles.bellBtnCount} style={{ background: visibleTriggers.length > 0 ? '#ef4444' : '#f59e0b' }}>
                        {globalCount > 9 ? '9+' : globalCount}
                    </span>
                )}
            </button>

            {open && (
                <div className={styles.panel}>
                    <div className={styles.tabs}>
                        {TABS.map(tab => {
                            const isActive = activeTab === tab.id;
                            return (
                                <button
                                    key={tab.id}
                                    onClick={() => setActiveTab(tab.id)}
                                    className={`${styles.tabBtn} ${isActive ? styles.tabBtnActive : ''}`}
                                >
                                    {tab.icon}
                                    {tab.label}
                                    {'count' in tab && tab.count !== undefined && tab.count > 0 && (
                                        <span className={`${styles.badge} ${tab.id === 'aguardando' ? styles.badgeWarning : ''}`}>
                                            {tab.count}
                                        </span>
                                    )}
                                </button>
                            );
                        })}
                    </div>

                    <div className={styles.scrollArea}>
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
                                        <RefreshCw size={24} className="spin" style={{ opacity: 0.3, margin: '0 auto', color: 'var(--sw-accent)', display: 'block' }} />
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

                    <div className={styles.footer}>
                        <div className={styles.statusInfo}>
                            <div className={styles.statusDot} />
                            <span className={styles.statusText}>System Live</span>
                        </div>
                        <button onClick={fetchActivities} className={styles.refreshBtn}>
                            <RefreshCw size={11} className={loadingActivities ? 'spin' : ''} />
                            Atualizar
                        </button>
                    </div>
                </div>
            )}
            <style>{`
                .spin {
                    animation: spin 1s linear infinite;
                }
                @keyframes spin {
                    from { transform: rotate(0deg); }
                    to   { transform: rotate(360deg); }
                }
            `}</style>
        </div>
    );
};

const EmptyState: React.FC<{ icon: React.ReactNode; title: string; subtitle: string }> = ({ icon, title, subtitle }) => (
    <div className={styles.emptyState}>
        <div className={styles.emptyIcon}>{icon}</div>
        <span className={styles.emptyTitle}>{title}</span>
        <span className={styles.emptySubtitle}>{subtitle}</span>
    </div>
);

export default TriggerNotifications;
