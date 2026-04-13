import React, { useState, useMemo } from 'react';
import { 
    Phone, 
    Mail, 
    Calendar, 
    MessageSquare, 
    FileText, 
    CheckCircle2, 
    Clock, 
    ArrowRight, 
    User,
    Building2,
    Check
} from 'lucide-react';
import styles from './HistoryTimeline.module.css';

interface HistoryTimelineProps {
    details: {
        activities: any[];
        notes: any[];
        updates: any[];
        persons: any[];
    };
    orgName: string;
}

type TimelineEvent = {
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

export const HistoryTimeline: React.FC<HistoryTimelineProps> = ({ details, orgName }) => {
    const [activeTab, setActiveTab] = useState('Todos');

    // Consolidar e normalizar eventos
    const events = useMemo(() => {
        if (!details) return [];

        const result: TimelineEvent[] = [];

        // 1. Processar Atividades
        (details.activities || []).forEach(act => {
            result.push({
                id: `act-${act.id}`,
                type: 'activity',
                timestamp: act.add_time || act.due_date,
                title: act.subject || 'Tarefa',
                user: act.owner_name,
                contact: act.person_name,
                company: act.org_name || orgName,
                content: act.note,
                done: act.done === 1,
                activityType: act.type,
                icon: act.type === 'call' ? <Phone size={14} /> : 
                      act.type === 'meeting' ? <Calendar size={14} /> : 
                      act.type === 'email' ? <Mail size={14} /> : <CheckCircle2 size={14} />
            });
        });

        // 2. Processar Notas
        (details.notes || []).forEach(note => {
            result.push({
                id: `note-${note.id}`,
                type: 'note',
                timestamp: note.add_time,
                title: 'Anotação',
                user: note.user?.name,
                contact: note.person?.name,
                company: orgName,
                content: note.content,
                icon: <MessageSquare size={14} />
            });
        });

        // 3. Processar Updates (Registro de alterações)
        (details.updates || []).forEach(upd => {
            if (upd.type === 'activity' || upd.type === 'note') return; // Evitar duplicidade

            result.push({
                id: `upd-${upd.id}`,
                type: 'update',
                timestamp: upd.timestamp || upd.add_time,
                title: upd.data?.field_name ? `Alterado: ${upd.data.field_name}` : 'Atualização de Sistema',
                subtext: upd.data?.old_value && upd.data?.new_value ? 
                         `${upd.data.old_value} → ${upd.data.new_value}` : '',
                user: upd.user_name || 'Sistema',
                icon: <Clock size={14} />
            });
        });

        // Ordenar por data decrescente
        return result.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
    }, [details, orgName]);

    const tabs = ['Todos', 'Anotações', 'Atividades', 'Histórico'];

    const filteredEvents = events.filter(e => {
        if (activeTab === 'Todos') return true;
        if (activeTab === 'Anotações') return e.type === 'note';
        if (activeTab === 'Atividades') return e.type === 'activity';
        if (activeTab === 'Histórico') return e.type === 'update';
        return true;
    });

    const formatDateTime = (ts: string) => {
        if (!ts) return '';
        const d = new Date(ts);
        return d.toLocaleDateString('pt-BR', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' });
    };

    return (
        <div className={styles.container}>
            <div className={styles.timeline}>
                {events.length === 0 && (
                    <div className={styles.empty}>Nenhum registro encontrado para este negócio.</div>
                )}
                {events.map((event, idx) => (
                    <div key={event.id} className={styles.eventRow}>
                        {/* Linha e Ícone Lateral */}
                        <div className={styles.timelineSide}>
                            <div className={styles.iconCircle}>
                                {event.icon}
                            </div>
                            {idx < filteredEvents.length - 1 && <div className={styles.dashedLine} />}
                        </div>

                        {/* Conteúdo do Card */}
                        <div className={styles.eventCard}>
                            <div className={styles.eventHeader}>
                                <div className={styles.titleArea}>
                                    {event.done && <Check size={12} className={styles.doneCheck} />}
                                    <span className={styles.eventTitle}>{event.title}</span>
                                </div>
                                <span className={styles.moreOptions}>•••</span>
                            </div>

                            <div className={styles.eventMeta}>
                                <span className={styles.metaItem}>{formatDateTime(event.timestamp)}</span>
                                {event.user && <span className={styles.metaSeparator}>•</span>}
                                {event.user && <span className={styles.metaItem}>{event.user}</span>}
                                {event.contact && (
                                    <>
                                        <span className={styles.metaSeparator}>•</span>
                                        <span className={styles.metaItem}><User size={10} /> {event.contact}</span>
                                    </>
                                )}
                                <span className={styles.metaSeparator}>•</span>
                                <span className={styles.metaItem}><Building2 size={10} /> {event.company}</span>
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
                ))}
            </div>
        </div>
    );
};
