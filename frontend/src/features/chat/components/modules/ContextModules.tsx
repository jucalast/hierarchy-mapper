import React from 'react';
import { 
    Phone, Mail, Calendar, CheckCircle2, User2, Building2, DollarSign, Check, Clock 
} from 'lucide-react';
import { TimelineEventRow, TimelineEvent } from '@/features/prospecting/components/TimelineEventRow';
import { PersonaCard } from '@/features/prospecting/components/PersonaCard';
import { CompactEmployeeCard } from '@/features/network-graph/components/CompactEmployeeCard';
import { Avatar } from '@/components/ui';
import { OrgListItem } from '@/features/prospecting/components/OrgListItem';
import styles from '../../styles/components/AgentV2Message.module.css';

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
        <div className={styles.taskList}>
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
                    <div key={event.id}>
                        <TimelineEventRow 
                            event={event} 
                            isLast={isLastInBlock} 
                            hasBackground={true} 
                        />
                    </div>
                );
            })}
            {tasks.length > 15 && (
                <div className={styles.emptyModule} style={{ textAlign: 'center', marginTop: '8px' }}>
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
            <div className={styles.contactGrid}>
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

    // Normalizar o logo: busca em todas as variações de campo que a IA pode enviar
    const resolvedLogo =
        org.logo ||
        org.confirmedLogo ||
        org.logo_url ||
        org.company_logo ||
        org.organization_logo ||
        org.brand_logo ||
        org.company_image ||
        org.linkedin_metadata?.logo ||
        (org.domain ? `https://unavatar.io/${org.domain}` : null) ||
        null;

    const normalizedOrg = resolvedLogo ? { ...org, logo: resolvedLogo } : org;

    // Extrair dados de employees se disponíveis
    const displayCount = org.employees_count || org.employee_count || org.mapped_count || 0;
    const displayPics = (org.employees || org.decision_makers || [])
        .map((dm: any) => dm.profile_pic || dm.avatar)
        .filter(Boolean) || [];

    // Renderizar OrgListItem diretamente sem wrapper nem className extra
    // Adiciona classe noHover para remover borda no hover no chat
    // Passa isSelected={true} para forçar exibição do footer de employees
    return (
        <OrgListItem
            org={normalizedOrg}
            showExpandToggle={false}
            className="noHover"
            displayCount={displayCount}
            displayPics={displayPics}
            isSelected={true}
        />
    );
};

export const ContactPill: React.FC<{ data: any }> = ({ data }) => {
    if (!data) return null;
    
    const name = data.name || data.name_clean || 'Contato';
    
    // Extração segura de subtexto (Pipedrive pode retornar arrays de objetos)
    const getSafeValue = (val: any) => {
        if (!val) return null;
        if (typeof val === 'string') return val;
        if (Array.isArray(val) && val.length > 0) {
            const first = val[0];
            return typeof first === 'object' ? first.value : first;
        }
        if (typeof val === 'object') return val.value || JSON.stringify(val);
        return String(val);
    };

    const subtext = getSafeValue(data.email) || getSafeValue(data.phone) || data.department || 'Mapeado';
    
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
        <div className={`${styles.inputCompanyPill} ${styles.glassModuleCard}`} style={{ cursor: 'default' }}>
            <div className={styles.pillIconArea}>
                {showEmail ? (
                    <img src="/outlook.png" alt="E" className={styles.pillCompanyLogo} style={{ background: 'transparent' }} />
                ) : showWhatsApp ? (
                    <img src="/wppicon.png" alt="W" className={styles.pillCompanyLogo} style={{ background: 'transparent' }} />
                ) : (
                    <User2 size={14} color="#94a3b8" />
                )}
            </div>
            <div className={styles.pillInfo}>
                <span className={styles.pillName}>{name}</span>
                <span className={styles.pillSubtext}>{subtext}</span>
            </div>
        </div>
    );
};
