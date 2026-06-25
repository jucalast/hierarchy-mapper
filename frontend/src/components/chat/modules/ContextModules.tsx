import React from 'react';
import {
    Phone, Mail, Calendar, CheckCircle2, User2, ClipboardList, Users
} from 'lucide-react';
import { TimelineEventRow, TimelineEvent } from '../../prospecting/TimelineEventRow';
import { PersonaCard } from '../../prospecting/PersonaCard';
import { CompactEmployeeCard } from '../../network-graph/CompactEmployeeCard';
import { OrgListItem } from '../../prospecting/OrgListItem';
import styles from '../ChatPanel.module.css';
import ctx from './ContextModules.module.css';

/* ─── TaskList ───────────────────────────────────────────────── */
export const TaskList: React.FC<{ data: any }> = ({ data }) => {
    const tasks = data?.today_tasks || data?.activities || [];
    if (!tasks.length) return <div className={ctx.empty}>Nenhuma tarefa encontrada.</div>;

    const activityToEvent = (task: any): TimelineEvent => {
        const getIcon = (type: string) => {
            if (type === 'call') return <Phone size={13} />;
            if (type === 'email') return <Mail size={13} />;
            return <Calendar size={13} />;
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

    const visibleTasks = tasks.slice(0, 15);

    return (
        <div className={ctx.taskSection}>
            <div className={ctx.sectionHeader}>
                <ClipboardList size={12} color="var(--sw-text-subtle)" />
                <span className={ctx.sectionLabel}>Atividades</span>
                {tasks.length > 0 && (
                    <span className={ctx.sectionCount}>{Math.min(tasks.length, 15)}</span>
                )}
            </div>

            <div className={ctx.taskWrapper}>
                {visibleTasks.map((task: any, i: number) => {
                    const event = activityToEvent(task);
                    const nextTask = tasks[i + 1];

                    const getDealId = (t: any) => {
                        if (!t) return null;
                        const d = t.deal_id;
                        return (typeof d === 'object' && d !== null) ? d.value : d;
                    };

                    const currentDealId = getDealId(task);
                    const nextDealId = getDealId(nextTask);
                    const isLastInBlock = i === visibleTasks.length - 1 || !currentDealId || currentDealId !== nextDealId;

                    return (
                        <div key={event.id}>
                            <TimelineEventRow
                                event={event}
                                isLast={isLastInBlock}
                                hasBackground={false}
                            />
                        </div>
                    );
                })}
            </div>

            {tasks.length > 15 && (
                <div className={ctx.empty} style={{ textAlign: 'center', marginTop: 6 }}>
                    Exibindo 15 de {tasks.length} tarefas.
                </div>
            )}
        </div>
    );
};

/* ─── ContactGrid ────────────────────────────────────────────── */
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
                location: osint.notas || 'Lead Enriquecido',
                department: 'Enriquecimento OSINT',
            };
            return (
                <div className={ctx.contactSection}>
                    <div className={ctx.sectionHeader}>
                        <User2 size={12} color="var(--sw-text-subtle)" />
                        <span className={ctx.sectionLabel}>Contato Enriquecido</span>
                    </div>
                    <PersonaCard data={singlePersona} />
                </div>
            );
        }
        return <div className={ctx.empty}>Nenhum contato encontrado.</div>;
    }

    return (
        <div className={ctx.contactSection}>
            <div className={ctx.sectionHeader}>
                <Users size={12} color="var(--sw-text-subtle)" />
                <span className={ctx.sectionLabel}>Decisores</span>
                <span className={ctx.sectionCount}>{contacts.length}</span>
            </div>
            <div className={ctx.contactGridInner}>
                {contacts.map((c: any, i: number) => (
                    <CompactEmployeeCard key={i} data={c} />
                ))}
            </div>
        </div>
    );
};

/* ─── CompanyCard ────────────────────────────────────────────── */
export const CompanyCard: React.FC<{ data: any }> = ({ data }) => {
    const org = data?.organization || data?.org_id || data?.org || data?.company || (data?.id && data?.name ? data : null);
    if (!org) return null;

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
    const displayCount = org.employees_count || org.employee_count || org.mapped_count || 0;
    const displayPics = (org.employees || org.decision_makers || [])
        .map((dm: any) => dm.profile_pic || dm.avatar)
        .filter(Boolean) || [];

    return (
        <div className={ctx.companySection}>
            <OrgListItem
                org={normalizedOrg}
                showExpandToggle={false}
                className="noHover"
                displayCount={displayCount}
                displayPics={displayPics}
                isSelected={true}
            />
        </div>
    );
};

/* ─── ContactPill ────────────────────────────────────────────── */
export const ContactPill: React.FC<{ data: any }> = ({ data }) => {
    if (!data) return null;

    const name = data.name || data.name_clean || 'Contato';

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

    const channels = data.channels || [];
    const isEmailPrimary = channels.includes('Email') || !!data.email;
    const hasWhatsApp = data.whatsapp_available || (channels.includes('WhatsApp') && !!data.phone);
    const showWhatsApp = hasWhatsApp && !isEmailPrimary;
    const showEmail = isEmailPrimary;

    // Cor do accent bar por canal
    const accentColor = showEmail
        ? '#0078d4'           // azul Outlook
        : showWhatsApp
            ? '#25d366'       // verde WhatsApp
            : 'var(--sw-primary)';

    // Cor do channelBox
    const channelBg = showEmail
        ? 'rgba(0, 120, 212, 0.12)'
        : showWhatsApp
            ? 'rgba(37, 211, 102, 0.12)'
            : 'var(--sw-primary-soft)';

    return (
        <div
            className={ctx.contactCard}
            style={{ '--accentColor': accentColor } as React.CSSProperties}
        >
            <div className={ctx.channelBox} style={{ background: channelBg }}>
                {showEmail ? (
                    <img src="/outlook.png" alt="Email" className={ctx.channelImg} />
                ) : showWhatsApp ? (
                    <img src="/wppicon.png" alt="WhatsApp" className={ctx.channelImg} />
                ) : (
                    <User2 size={14} color="var(--sw-primary)" />
                )}
            </div>

            <div className={ctx.contactInfo}>
                <span className={ctx.contactName}>{name}</span>
                <span className={ctx.contactSubtext}>{subtext}</span>
            </div>

            <span className={ctx.contactBadge}>Contato</span>
        </div>
    );
};
