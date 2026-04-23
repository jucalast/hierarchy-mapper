import React from 'react';
import { 
    Phone, Mail, Calendar, CheckCircle2, User2, Building2, DollarSign, Check, Clock 
} from 'lucide-react';
import { TimelineEventRow, TimelineEvent } from '../../TimelineEventRow';
import { PersonaCard } from '../../PersonaCard';
import { CompactEmployeeCard } from '../../CompactEmployeeCard';
import { Avatar } from '../../ui';
import { OrgListItem } from '../../OrgListItem';
import styles from '../../ChatPanel.module.css'; 

export const TaskList: React.FC<{ data: any }> = ({ data }) => {
    const tasks = data?.today_tasks || data?.activities || [];
    if (!tasks.length) return <div className={styles.emptyModule} style={{ padding: '20px', textAlign: 'center', opacity: 0.5, fontSize: '13px' }}>Nenhuma tarefa encontrada.</div>;

    const activityToEvent = (task: any): TimelineEvent => {
        const getIcon = (type: string) => {
            if (type === 'call') return <Phone size={14} />;
            if (type === 'email') return <Mail size={14} />;
            return <Calendar size={14} />;
        };
        return {
            id: task.id || Math.random(),
            type: 'activity',
            timestamp: task.due_date || '',
            title: task.subject || 'Tarefa',
            user: task.owner_name,
            contact: task.person_name,
            company: task.org_name,
            content: task.note_clean || task.note,
            done: task.done === true || task.done === 1,
            activityType: task.type,
            icon: getIcon(task.type),
        };
    };

    return (
        <div className={styles.taskList} style={{ marginTop: '12px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
            {tasks.slice(0, 15).map((task: any, i: number) => {
                const event = activityToEvent(task);
                const nextTask = tasks[i + 1];
                
                // Extração segura de Deal ID para comparação de agrupamento
                const getDealId = (t: any) => {
                    if (!t) return null;
                    const d = t.deal_id;
                    return (typeof d === 'object' && d !== null) ? d.value : d;
                };
                
                const currentDealId = getDealId(task);
                const nextDealId = getDealId(nextTask);
                
                // Só ligamos com linha se pertencerem ao MESMO negócio e não for o último da lista
                const isLastInBlock = i === Math.min(tasks.length, 15) - 1 || !currentDealId || currentDealId !== nextDealId;

                return (
                    <div key={event.id} style={{ marginLeft: '16px' }}>
                        <TimelineEventRow 
                            event={event} 
                            isLast={isLastInBlock} 
                            hasBackground={true} 
                        />
                    </div>
                );
            })}
            {tasks.length > 15 && (
                <div style={{ fontSize: '11px', color: '#9ca3af', textAlign: 'center', marginTop: '8px', fontStyle: 'italic', opacity: 0.8 }}>
                    Exibindo 15 de {tasks.length} tarefas. Use o Pipedrive para ver a lista completa.
                </div>
            )}
        </div>
    );
};

export const ContactGrid: React.FC<{ data: any }> = ({ data }) => {
    const contacts = data?.decision_makers || data?.persons || [];

    if (!contacts.length) {
        const osint = data?.osint_result;
        if (osint && osint.lead) {
            const singlePersona = {
                name: osint.lead,
                company: osint.empresa,
                phone: osint.whatsapp?.numero || osint.pabx || osint.contatosSede,
                email: osint.emailProvavel,
                location: osint.notas || "Lead Enriquecido",
                department: "Enriquecimento OSINT"
            };
            return (
                <div className={styles.moduleContainer}>
                    <div className={styles.moduleHeader}><User2 size={16} /> <span>Contato Enriquecido</span></div>
                    <div className={styles.contactGrid} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        <PersonaCard data={singlePersona} />
                    </div>
                </div>
            );
        }
        return <div className={styles.emptyModule}>Nenhum contato encontrado.</div>;
    }

    return (
        <div className={styles.moduleContainer}>
            <div className={styles.contactGrid} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {contacts.map((c: any, i: number) => (
                    <CompactEmployeeCard key={i} data={c} />
                ))}
            </div>
        </div>
    );
};

export const CompanyCard: React.FC<{ data: any }> = ({ data }) => {
    // Tentar extrair o objeto da empresa de várias formas possíveis nos logs
    const org = data?.organization || data?.org_id || data?.org || data?.company || (data?.id && data?.name ? data : null);
    if (!org) return null;

    // OrgListItem agora lida com a extração de displayCount e displayPics internamente
    return (
        <OrgListItem
            org={org}
            showExpandToggle={false}
            className=""
            style={{ padding: '8px 0', border: 'none', boxShadow: 'none' }}
        />
    );
};

export const ContactPill: React.FC<{ data: any }> = ({ data }) => {
    if (!data) return null;
    
    const name = data.name || data.name_clean || 'Contato';
    const subtext = data.email || data.phone || data.department || 'Mapeado';
    
    // Identificação de canal prioritário
    const channels = data.channels || [];
    const isWhatsAppPrimary = channels.includes('WhatsApp') && !channels.includes('Email');
    const isEmailPrimary = channels.includes('Email') || !!data.email;
    const hasWhatsApp = data.whatsapp_available || (channels.includes('WhatsApp') && !!data.phone);

    // Se tiver E-mail, damos prioridade ao ícone do Outlook (especialmente se for a fonte principal)
    // Se tiver APENAS WhatsApp ou for explicitamente prioridade WA, usamos WPP.
    const showWhatsApp = hasWhatsApp && !isEmailPrimary;
    const showEmail = isEmailPrimary;

    return (
        <div className={`${styles.inputCompanyPill} ${styles.glassModuleCard}`} style={{ margin: '4px 0', cursor: 'default' }}>
            <div className={styles.pillIconArea} style={{ width: '20px', height: '20px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                {showEmail ? (
                    <img src="/outlook.png" alt="E" style={{ width: 18, height: 18, objectFit: 'contain' }} />
                ) : showWhatsApp ? (
                    <img src="/wppicon.png" alt="W" style={{ width: 18, height: 18, objectFit: 'contain' }} />
                ) : (
                    <User2 size={14} color="#94a3b8" />
                )}
            </div>
            <div className={styles.pillInfo} style={{ marginLeft: '8px' }}>
                <span className={styles.pillName} style={{ fontSize: '13px', fontWeight: '600' }}>{name}</span>
                <span className={styles.pillSubtext} style={{ fontSize: '11px', opacity: 0.7 }}>{subtext}</span>
            </div>
        </div>
    );
};
