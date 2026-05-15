import React from 'react';
import { Loader2, RefreshCw, Mail, MessageSquare, ArrowRight, CornerDownLeft, CheckCheck, AlertCircle } from 'lucide-react';
import type { ActivityOut } from '@/services/api/conversations';
import styles from '../styles/components/ActivitySidebar.module.css';

interface ActivitySidebarProps {
    activities: ActivityOut[];
    isLoading: boolean;
    onRefresh: () => void;
    onClose: () => void;
}

// Formata data relativa: "agora", "14:33", "ontem", "19 Abr"
function formatRelativeDate(isoStr: string): string {
    const date = new Date(isoStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    const diffH = Math.floor(diffMs / 3600000);

    if (diffMin < 2) return 'agora';
    if (diffMin < 60) return `${diffMin}m`;
    if (diffH < 24 && date.getDate() === now.getDate()) {
        return date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    }
    const yesterday = new Date(now);
    yesterday.setDate(now.getDate() - 1);
    if (date.getDate() === yesterday.getDate()) return 'ontem';
    return date.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' }).replace('.', '');
}

// Agrupa atividades por dia
function groupByDay(activities: ActivityOut[]): { label: string; items: ActivityOut[] }[] {
    const groups: Record<string, ActivityOut[]> = {};
    const now = new Date();

    for (const act of activities) {
        const d = new Date(act.created_at);
        let key: string;
        if (d.toDateString() === now.toDateString()) key = 'Hoje';
        else {
            const yesterday = new Date(now);
            yesterday.setDate(now.getDate() - 1);
            if (d.toDateString() === yesterday.toDateString()) key = 'Ontem';
            else key = d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' }).replace('.', '');
        }
        if (!groups[key]) groups[key] = [];
        groups[key].push(act);
    }

    return Object.entries(groups).map(([label, items]) => ({ label, items }));
}

function ActivityIcon({ type, status }: { type: string; status: string }) {
    const iconProps = { size: 10 };
    if (type === 'email_sent' || type === 'email_reply_sent') {
        return <Mail {...iconProps} />;
    }
    if (type === 'email_reply_received') {
        return <CornerDownLeft {...iconProps} />;
    }
    if (type === 'whatsapp_sent' || type === 'whatsapp_received') {
        return <MessageSquare {...iconProps} />;
    }
    if (type === 'stage_changed') {
        return <ArrowRight {...iconProps} />;
    }
    if (status === 'awaiting_reply') {
        return <AlertCircle {...iconProps} />;
    }
    return <CheckCheck {...iconProps} />;
}

function activityIconClass(type: string, status: string): string {
    if (type.startsWith('email')) return styles.asIconEmail;
    if (type.startsWith('whatsapp')) return styles.asIconWhatsapp;
    if (type === 'stage_changed') return styles.asIconStage;
    if (status === 'awaiting_reply') return styles.asIconPending;
    return styles.asIconDefault;
}

function activityLabel(act: ActivityOut): string {
    const p = act.payload || {};
    switch (act.activity_type) {
        case 'email_sent':
            return `Email → ${p.to_name || p.to_email || '?'}`;
        case 'email_reply_sent':
            return `Resposta → ${p.to_name || '?'}`;
        case 'email_reply_received':
            return `Resposta de ${p.from_name || '?'}`;
        case 'whatsapp_sent':
            return `WA → ${p.to_name || '?'}`;
        case 'whatsapp_received':
            return `WA de ${p.from_name || '?'}`;
        case 'stage_changed':
            return `${p.from_stage || '?'} → ${p.to_stage || '?'}`;
        default:
            return act.activity_type.replace(/_/g, ' ');
    }
}

function activitySubLabel(act: ActivityOut): string {
    const p = act.payload || {};
    if (act.activity_type.startsWith('email')) return p.subject || '';
    if (act.activity_type.startsWith('whatsapp')) return (p.message_preview || '').slice(0, 48);
    if (act.activity_type === 'stage_changed') return p.deal_title || '';
    return '';
}

function statusBadge(status: string) {
    if (status === 'awaiting_reply') return <span className={`${styles.asStatusBadge} ${styles.asStatusAwaiting}`}>aguardando</span>;
    if (status === 'replied') return <span className={`${styles.asStatusBadge} ${styles.asStatusReplied}`}>respondido</span>;
    if (status === 'cancelled') return <span className={`${styles.asStatusBadge} ${styles.asStatusCancelled}`}>cancelado</span>;
    if (status === 'failed') return <span className={`${styles.asStatusBadge} ${styles.asStatusFailed}`}>erro</span>;
    return null;
}

export const ActivitySidebar: React.FC<ActivitySidebarProps> = ({
    activities,
    isLoading,
    onRefresh,
    onClose,
}) => {
    const groups = groupByDay(activities);

    return (
        <div className={styles.activitySidebar}>
            <div className={styles.asHeader}>
                <span className={styles.asTitle}>Atividades</span>
                {activities.length > 0 && <span className={styles.asCount}>{activities.length}</span>}
                <div style={{ flex: 1 }} />
                <button className={styles.asRefreshBtn} onClick={onRefresh} disabled={isLoading} title="Atualizar">
                    {isLoading ? <Loader2 size={11} className={styles.spinner} /> : <RefreshCw size={11} />}
                </button>
            </div>

            <div className={styles.asList}>
                {isLoading && activities.length === 0 && (
                    <div className={styles.asEmptyState}>
                        <Loader2 size={14} className={styles.spinner} />
                        <span>Carregando...</span>
                    </div>
                )}
                {!isLoading && activities.length === 0 && (
                    <div className={styles.asEmptyState}>
                        <span>Nenhuma atividade registrada</span>
                    </div>
                )}
                {groups.map(group => (
                    <React.Fragment key={group.label}>
                        <div className={styles.asDivider}>{group.label}</div>
                        {group.items.map(act => (
                            <div key={act.id} className={`${styles.asItem} ${act.status === 'awaiting_reply' ? styles.asItemPending : ''}`}>
                                <div className={styles.asItemTop}>
                                    <div className={`${styles.asIcon} ${activityIconClass(act.activity_type, act.status)}`}>
                                        <ActivityIcon type={act.activity_type} status={act.status} />
                                    </div>
                                    <div className={styles.asItemLabel}>{activityLabel(act)}</div>
                                    <div className={styles.asItemDate}>{formatRelativeDate(act.created_at)}</div>
                                </div>
                                {activitySubLabel(act) && (
                                    <div className={styles.asItemSub}>{activitySubLabel(act)}</div>
                                )}
                                {statusBadge(act.status)}
                            </div>
                        ))}
                    </React.Fragment>
                ))}
            </div>
        </div>
    );
};
