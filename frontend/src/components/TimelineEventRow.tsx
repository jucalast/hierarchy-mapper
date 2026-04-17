import React from 'react';
import { 
    User, Building2, Check 
} from 'lucide-react';
import styles from './HistoryTimeline.module.css';

export type TimelineEvent = {
    id: string | number;
    type: 'activity' | 'note' | 'update';
    timestamp: string;
    title: string;
    subtext?: string;
    content?: string;
    user?: string;
    contact?: string;
    company?: string;
    icon: React.ReactNode;
    done?: boolean;
    activityType?: string;
};

interface TimelineEventRowProps {
    event: TimelineEvent;
    isLast?: boolean;
    hasBackground?: boolean;
}

export const TimelineEventRow: React.FC<TimelineEventRowProps> = ({ event, isLast, hasBackground }) => {
    const formatDateTime = (ts: string) => {
        if (!ts) return '';
        try {
            const d = new Date(ts);
            if (isNaN(d.getTime())) return ts;
            
            const day = d.getDate();
            const month = d.toLocaleDateString('pt-BR', { month: 'long' });
            
            // Se for apenas data (sem hora relevante ou informada como 00:00:00)
            const hasTime = ts.includes('T') || ts.includes(':') || ts.includes(' ');
            
            if (!hasTime) {
                return `${day} de ${month}`;
            }

            const hours = d.getHours().toString().padStart(2, '0');
            const minutes = d.getMinutes().toString().padStart(2, '0');
            
            return `${day} de ${month} às ${hours}:${minutes}`;
        } catch (e) {
            return ts;
        }
    };

    // Helper para renderizar itens com separadores
    const metaItems = [];
    if (event.timestamp) metaItems.push(<span className={styles.metaItem}>{formatDateTime(event.timestamp)}</span>);
    if (event.user) metaItems.push(<span className={styles.metaItem}>{event.user}</span>);
    if (event.contact) metaItems.push(
        <span className={styles.metaItem}>
            <User size={10} /> {event.contact}
        </span>
    );
    if (event.company) metaItems.push(
        <span className={styles.metaItem}>
            <Building2 size={10} /> {event.company}
        </span>
    );

    return (
        <div className={styles.eventRow}>
            {/* Linha e Ícone Lateral */}
            <div className={styles.timelineSide}>
                <div className={`${styles.iconCircle} ${event.done ? styles.iconCircleDone : ''}`}>
                    {event.icon}
                </div>
                {!isLast && <div className={styles.dashedLine} />}
            </div>

            {/* Conteúdo do Card */}
            <div className={`${styles.eventCard} ${event.done ? styles.eventCardDone : ''} ${hasBackground ? styles.cardWithBg : ''}`}>
                <div className={styles.eventHeader}>
                    <div className={styles.titleArea}>
                        {event.done && <Check size={12} className={styles.doneCheck} />}
                        <span className={styles.eventTitle}>{event.title}</span>
                    </div>
                    <span className={styles.moreOptions}>•••</span>
                </div>

                <div className={styles.eventMeta}>
                    {metaItems.map((item, index) => (
                        <React.Fragment key={index}>
                            {item}
                            {index < metaItems.length - 1 && <span className={styles.metaSeparator}>•</span>}
                        </React.Fragment>
                    ))}
                </div>

                {event.subtext && (
                    <div className={styles.eventSubtext}>
                        {event.subtext}
                    </div>
                )}

                {event.content && (
                    <div className={`${styles.eventContent} ${event.activityType === 'call' || event.type === 'note' ? styles.callNote : ''}`}>
                        <div dangerouslySetInnerHTML={{ __html: event.content }} />
                    </div>
                )}
            </div>
        </div>
    );
};
