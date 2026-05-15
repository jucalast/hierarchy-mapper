import React, { useState } from 'react';
import { 
    User, Building2, Check, Sparkles
} from 'lucide-react';
import styles from './HistoryTimeline.module.css';

export type TimelineEvent = {
    id: string | number;
    type: 'activity' | 'note' | 'update';
    timestamp: string;
    dueDate?: string;
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
    const [showMenu, setShowMenu] = useState(false);
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
                <div className={styles.eventHeader} style={{ position: 'relative' }}>
                    <div className={styles.titleArea}>
                        {event.done && <Check size={12} className={styles.doneCheck} />}
                        <span className={styles.eventTitle}>{event.title}</span>
                    </div>
                    <div style={{ position: 'relative' }}>
                        <span 
                            className={styles.moreOptions}
                            onClick={(e) => {
                                e.stopPropagation();
                                setShowMenu(prev => !prev);
                            }}
                            style={{ 
                                padding: '4px 8px', 
                                borderRadius: 4, 
                                background: showMenu ? 'var(--sw-hover)' : 'transparent',
                                color: showMenu ? 'var(--sw-text-base)' : undefined,
                            }}
                        >
                            •••
                        </span>
                        {showMenu && (
                            <>
                                {/* Overlay invisível para fechar ao clicar fora */}
                                <div 
                                    style={{
                                        position: 'fixed',
                                        top: 0,
                                        left: 0,
                                        right: 0,
                                        bottom: 0,
                                        zIndex: 999,
                                        cursor: 'default',
                                    }}
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        setShowMenu(false);
                                    }}
                                />
                                <div 
                                    style={{
                                        position: 'absolute',
                                        right: 0,
                                        top: '100%',
                                        marginTop: 4,
                                        background: 'var(--sw-sidebar)',
                                        backdropFilter: 'blur(12px)',
                                        border: '1px solid var(--sw-border)',
                                        borderRadius: 8,
                                        boxShadow: 'var(--sw-shadow)',
                                        zIndex: 1000,
                                        minWidth: 160,
                                        overflow: 'hidden',
                                    }}
                                    onClick={(e) => e.stopPropagation()}
                                >
                                    <button
                                        onClick={() => {
                                            setShowMenu(false);
                                            // Mapeia títulos de atividade Pipedrive para instruções claras
                                            const titleLower = event.title.toLowerCase();
                                            let taskInstruction = `realizar a tarefa "${event.title}"`;
                                            if (titleLower.includes('encontrar contato') || titleLower.includes('encontrar decisor')) {
                                                taskInstruction = `encontrar o contato/decisor real da empresa${event.company ? ` ${event.company}` : ''}. Se não houver contato com canal válido cadastrado no CRM, abra o mapeador de hierarquia (open_hierarchy_drawer) para identificar o decisor`;
                                            } else if (titleLower.includes('ligar') || titleLower.includes('ligação')) {
                                                taskInstruction = `executar a ligação "${event.title}"${event.contact ? ` com ${event.contact}` : ''}`;
                                            } else if (titleLower.includes('enviar') || titleLower.includes('email') || titleLower.includes('whatsapp')) {
                                                taskInstruction = `executar o envio: "${event.title}"${event.contact ? ` para ${event.contact}` : ''}`;
                                            } else if (titleLower.includes('follow') || titleLower.includes('retorno') || titleLower.includes('cobrança')) {
                                                taskInstruction = `executar o follow-up "${event.title}"${event.contact ? ` com ${event.contact}` : ''}. Analise o histórico e execute a ação de comunicação mais adequada`;
                                            }
                                            const promptText = `Execute a seguinte atividade do CRM: ${taskInstruction}${event.company ? ` para a empresa ${event.company}` : ''}. Use as ferramentas para executar isso agora.`;
                                            window.dispatchEvent(new CustomEvent('submit_agent_prompt', { detail: { prompt: promptText } }));
                                        }}
                                        style={{
                                            width: '100%',
                                            padding: '10px 14px',
                                            background: 'transparent',
                                            border: 'none',
                                            color: 'var(--sw-text-base)',
                                            fontSize: '12px',
                                            fontWeight: 500,
                                            textAlign: 'left',
                                            cursor: 'pointer',
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: 8,
                                            transition: 'background 0.2s, color 0.2s',
                                        }}
                                        onMouseEnter={(e) => {
                                            e.currentTarget.style.background = 'var(--sw-hover)';
                                            e.currentTarget.style.color = 'var(--sw-text-base)';
                                        }}
                                        onMouseLeave={(e) => {
                                            e.currentTarget.style.background = 'transparent';
                                            e.currentTarget.style.color = 'var(--sw-text-base)';
                                        }}
                                    >
                                        <Sparkles size={12} />
                                        Fazer com o agente
                                    </button>
                                </div>
                            </>
                        )}
                    </div>
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
                    <div className={`${styles.eventContent} ${styles.callNote}`}>
                        <div dangerouslySetInnerHTML={{ __html: event.content }} />
                    </div>
                )}
            </div>
        </div>
    );
};
