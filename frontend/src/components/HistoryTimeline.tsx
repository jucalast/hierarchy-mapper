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
import { TimelineEventRow, TimelineEvent } from './TimelineEventRow';
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

 
 
export const HistoryTimeline: React.FC<HistoryTimelineProps> = ({ details, orgName }) => {
    const [activeTab, setActiveTab] = useState('Todos');

    // Consolidar e normalizar eventos (sem updates)
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
                done: act.done === true || act.done === 1,
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

        // Ordenar por data decrescente
        return result.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
    }, [details, orgName]);

    // Processar apenas Updates (Registro de alterações)
    const updates = useMemo(() => {
        if (!details?.updates) return [];

        const result: TimelineEvent[] = [];

        (details.updates || []).forEach((upd, index) => {
            if (upd.object === 'activity' || upd.object === 'note') return; // Evitar duplicidade

            result.push({
                id: `upd-${upd.data?.id || index}`,
                type: 'update',
                timestamp: upd.timestamp || upd.data?.add_time || upd.add_time,
                title: (upd.data?.field_name || upd.data?.field_key) ? `Alterado: ${upd.data?.field_name || upd.data?.field_key}` : 'Atualização de Sistema',
                subtext: upd.data?.old_value && upd.data?.new_value ? 
                         `${upd.data.old_value} → ${upd.data.new_value}` : '',
                user: upd.author?.name || upd.user_name || 'Sistema',
                icon: <Clock size={14} />
            });
        });

        return result.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
    }, [details]);

    const tabs = ['Todos', 'Anotações', 'Atividades'];

    const filteredEvents = events.filter(e => {
        if (activeTab === 'Todos') return true;
        if (activeTab === 'Anotações') return e.type === 'note';
        if (activeTab === 'Atividades') return e.type === 'activity';
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
                {filteredEvents.length === 0 && (
                    <div className={styles.empty}>Nenhum registro encontrado para esta aba.</div>
                )}
                {filteredEvents.map((event, idx) => (
                    <TimelineEventRow 
                        key={event.id} 
                        event={event} 
                        isLast={idx === filteredEvents.length - 1} 
                    />
                ))}
            </div>

            {/* Seção de Avisos (Updates) */}
            {updates.length > 0 && (
                <div className={styles.alertsSection}>
                    <div className={styles.alertsTitle}>Avisos de Sistema</div>
                    <div className={styles.alertsList}>
                        {updates.map((update) => (
                            <div key={update.id} className={styles.alertItem}>
                                <div className={styles.alertHeader}>
                                    <span className={styles.alertTitle}>{update.title}</span>
                                    <span className={styles.alertTime}>{formatDateTime(update.timestamp)}</span>
                                </div>
                                {update.subtext && (
                                    <div className={styles.alertSubtext}>{update.subtext}</div>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
};
