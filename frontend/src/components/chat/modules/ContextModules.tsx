import React from 'react';
import { 
    Phone, Mail, Calendar, CheckCircle2, User2, Building2 
} from 'lucide-react';
import { TimelineEventRow, TimelineEvent } from '../../TimelineEventRow';
import { PersonaCard } from '../../PersonaCard';
import { CompactEmployeeCard } from '../../CompactEmployeeCard';
import styles from '../../ChatPanel.module.css'; // Temporarily reuse styles

export const TaskList: React.FC<{ data: any }> = ({ data }) => {
    const tasks = data?.today_tasks || data?.activities || [];
    if (!tasks.length) return <div className={styles.emptyModule}>Nenhuma tarefa encontrada.</div>;

    const getIcon = (type: string) => {
        switch (type) {
            case 'call': return <Phone size={14} />;
            case 'meeting': return <Calendar size={14} />;
            case 'email': return <Mail size={14} />;
            default: return <CheckCircle2 size={14} />;
        }
    };

    return (
        <div className={styles.moduleContainer}>
            <div className={styles.taskList} style={{ marginTop: '16px' }}>
                {tasks.map((task: any, i: number) => {
                    const event: TimelineEvent = {
                        id: task.id || i,
                        type: 'activity',
                        timestamp: task.due_date || task.add_time || '',
                        title: task.subject || 'Tarefa',
                        user: task.owner_name,
                        contact: task.person_name,
                        company: task.org_name,
                        content: task.note,
                        done: task.done === true || task.done === 1,
                        activityType: task.type,
                        icon: getIcon(task.type)
                    };
                    return (
                        <TimelineEventRow
                            key={event.id}
                            event={event}
                            isLast={true}
                            hasBackground={true}
                        />
                    );
                })}
            </div>
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
    const org = data?.organization;
    if (!org) return null;
    return (
        <div className={styles.moduleContainer}>
            <div className={styles.moduleHeader}><Building2 size={16} /> <span>Dados Corporativos</span></div>
            <div className={styles.companyCard}>
                <div className={styles.companyInfoRow}><strong>CNPJ:</strong> <span>{org.cnpj || 'Não informado'}</span></div>
                <div className={styles.companyInfoRow}><strong>Site:</strong> <a href={org.domain} target="_blank" rel="noreferrer">{org.domain}</a></div>
                <div className={styles.companyInfoRow}><strong>Indústria:</strong> <span>{org.industry || 'N/A'}</span></div>
            </div>
        </div>
    );
};
