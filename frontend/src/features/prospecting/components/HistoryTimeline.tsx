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
    Check,
    AlertTriangle
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
            const dueStr = act.due_date || '';
            const timeStr = act.due_time || '';
            // Se tem due_date, monta o timestamp baseado nele. Caso contrário, usa add_time.
            const timestamp = dueStr ? `${dueStr}${timeStr ? `T${timeStr}` : 'T00:00:00'}` : act.add_time;

            result.push({
                id: `act-${act.id}`,
                type: 'activity',
                timestamp: timestamp,
                dueDate: dueStr,
                title: act.subject || 'Tarefa',
                user: act.owner_name || act.user_id?.name || act.user_name || 'Sistema',
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
                user: note.user?.name || note.user_id?.name || note.user_name || 'Sistema',
                contact: note.person?.name,
                company: orgName,
                content: note.content,
                icon: <MessageSquare size={14} />
            });
        });

        return result;
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

    // Agrupar eventos filtrados em categorias (Atrasadas, Hoje, Pra Frente, Histórico)
    const categories = useMemo(() => {
        const brToday = new Intl.DateTimeFormat('en-CA', {
            timeZone: 'America/Sao_Paulo',
            year: 'numeric',
            month: '2-digit',
            day: '2-digit'
        }).format(new Date()); // YYYY-MM-DD

        const overdue: TimelineEvent[] = [];
        const today: TimelineEvent[] = [];
        const upcoming: TimelineEvent[] = [];
        const history: TimelineEvent[] = [];

        filteredEvents.forEach(e => {
            if (e.type === 'note') {
                history.push(e);
            } else if (e.type === 'activity') {
                if (e.done) {
                    history.push(e);
                } else {
                    const dueDate = e.dueDate || '';
                    if (!dueDate) {
                        history.push(e); // Sem due_date vai pro histórico/sem data
                    } else if (dueDate < brToday) {
                        overdue.push(e);
                    } else if (dueDate === brToday) {
                        today.push(e);
                    } else {
                        upcoming.push(e);
                    }
                }
            }
        });

        // Ordenação por criticidade:
        // - Atrasadas: mais antigas primeiro (mais críticas!)
        overdue.sort((a, b) => (a.dueDate || '').localeCompare(b.dueDate || ''));
        // - Hoje: por hora/timestamp (mais recentes primeiro)
        today.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
        // - Pra frente: cronológica crescente (mais próximas primeiro)
        upcoming.sort((a, b) => (a.dueDate || '').localeCompare(b.dueDate || ''));
        // - Histórico: mais recentes primeiro
        history.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());

        return { overdue, today, upcoming, history };
    }, [filteredEvents]);

    const formatDateTime = (ts: string) => {
        if (!ts) return '';
        const d = new Date(ts);
        return d.toLocaleDateString('pt-BR', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' });
    };

    const hasAnyEvent = categories.overdue.length > 0 || 
                         categories.today.length > 0 || 
                         categories.upcoming.length > 0 || 
                         categories.history.length > 0;

    return (
        <div className={styles.container}>
            {/* Abas internas do histórico */}
            <div className={styles.tabs}>
                {tabs.map(tab => (
                    <button
                        key={tab}
                        className={activeTab === tab ? styles.activeTab : ''}
                        onClick={() => setActiveTab(tab)}
                    >
                        {tab}
                    </button>
                ))}
            </div>

            <div className={styles.timeline}>
                {!hasAnyEvent && (
                    <div className={styles.empty}>Nenhum registro encontrado para esta aba.</div>
                )}
                
                {categories.overdue.length > 0 && (
                    <div className={styles.section}>
                        <div className={`${styles.sectionHeader} ${styles.sectionOverdue}`}>
                            <AlertTriangle size={14} />
                            <span>Atrasadas ({categories.overdue.length})</span>
                        </div>
                        {categories.overdue.map((event, idx) => (
                            <TimelineEventRow 
                                key={event.id} 
                                event={event} 
                                isLast={idx === categories.overdue.length - 1} 
                            />
                        ))}
                    </div>
                )}

                {categories.today.length > 0 && (
                    <div className={styles.section}>
                        <div className={`${styles.sectionHeader} ${styles.sectionToday}`}>
                            <Clock size={14} />
                            <span>Hoje ({categories.today.length})</span>
                        </div>
                        {categories.today.map((event, idx) => (
                            <TimelineEventRow 
                                key={event.id} 
                                event={event} 
                                isLast={idx === categories.today.length - 1} 
                            />
                        ))}
                    </div>
                )}

                {categories.upcoming.length > 0 && (
                    <div className={styles.section}>
                        <div className={`${styles.sectionHeader} ${styles.sectionUpcoming}`}>
                            <ArrowRight size={14} />
                            <span>Pra Frente ({categories.upcoming.length})</span>
                        </div>
                        {categories.upcoming.map((event, idx) => (
                            <TimelineEventRow 
                                key={event.id} 
                                event={event} 
                                isLast={idx === categories.upcoming.length - 1} 
                            />
                        ))}
                    </div>
                )}

                {categories.history.length > 0 && (
                    <div className={styles.section}>
                        <div className={`${styles.sectionHeader} ${styles.sectionHistory}`}>
                            <CheckCircle2 size={14} />
                            <span>Histórico & Anotações ({categories.history.length})</span>
                        </div>
                        {categories.history.map((event, idx) => (
                            <TimelineEventRow 
                                key={event.id} 
                                event={event} 
                                isLast={idx === categories.history.length - 1} 
                            />
                        ))}
                    </div>
                )}
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
