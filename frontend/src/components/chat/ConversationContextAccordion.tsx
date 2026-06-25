import React, { useState, useMemo, useEffect } from 'react';
import {
    ChevronDown, Building2, Users,
    Briefcase, ClipboardList, MessageSquare, FileText,
    Target, Trash2
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import styles from './ChatPanel.module.css';
import { organizations } from '@/services/api';

interface ContextItem {
    id: string;
    title: string;
    icon: React.ReactNode;
    content: string;
    type: 'dossier' | 'org' | 'contacts' | 'deals' | 'activities' | 'messages' | 'evaluation';
}

interface ConversationContextAccordionProps {
    messages: any[];
    orgId?: number | null;
    orgName?: string;
    dealId?: number | null;
}

const TYPE_COLORS: Record<string, string> = {
    dossier:    '#a78bfa',
    org:        '#60a5fa',
    contacts:   '#2dd4bf',
    deals:      '#4ade80',
    activities: '#fbbf24',
    messages:   '#f87171',
    evaluation: '#818cf8',
};

export const ConversationContextAccordion: React.FC<ConversationContextAccordionProps> = ({
    messages,
    orgId,
    orgName,
    dealId,
}) => {
    const [isOpen, setIsOpen] = useState(false);
    const [openSections, setOpenSections] = useState<Set<string>>(new Set());
    const [dbPlan, setDbPlan] = useState<string | null>(null);

    useEffect(() => {
        if (orgId) {
            organizations.getLocalOrganization(orgId)
                .then(res => {
                    if (res && typeof res === 'object' && 'prospecting_context' in res && res.prospecting_context) {
                        setDbPlan(res.prospecting_context as string);
                    }
                })
                .catch(() => {});
        } else {
            setDbPlan(null);
        }
    }, [orgId]);

    const items = useMemo((): ContextItem[] => {
        const result: ContextItem[] = [];
        const seenTools = new Set<string>();

        if (orgId || orgName || dealId) {
            let scopeContent = '';
            if (orgName) scopeContent += `- **Empresa**: ${orgName}\n`;
            if (orgId)   scopeContent += `- **Org ID (Pipedrive)**: ${orgId}\n`;
            if (dealId)  scopeContent += `- **Deal ID**: ${dealId}\n`;
            result.push({ id: 'scope', title: 'Escopo da Sessão', icon: <Target size={13} />, content: scopeContent, type: 'evaluation' });
        }

        for (let i = messages.length - 1; i >= 0; i--) {
            const msg = messages[i];
            if (!msg.isAgent || !msg.agentEvents) continue;
            for (const event of msg.agentEvents) {
                if (event.type !== 'tool_result' || !event.tool || !event.summary || !event.ok) continue;
                const tool = event.tool;
                if (seenTools.has(tool)) continue;
                seenTools.add(tool);
                const detail = event.response || event.content || event.summary;

                if (tool === 'generate_dossier' || tool === 'deep_company_investigation') {
                    result.push({ id: 'dossier', title: 'Dossiê Estratégico', icon: <FileText size={13} />, content: detail, type: 'dossier' });
                } else if (tool === 'pipedrive_get_org') {
                    result.push({ id: 'org', title: 'Dados da Empresa (CRM)', icon: <Building2 size={13} />, content: detail, type: 'org' });
                } else if (tool === 'pipedrive_get_persons') {
                    result.push({ id: 'contacts', title: 'Contatos Identificados', icon: <Users size={13} />, content: event.summary, type: 'contacts' });
                } else if (tool === 'pipedrive_get_deals') {
                    result.push({ id: 'deals', title: 'Negócios em Aberto', icon: <Briefcase size={13} />, content: event.summary, type: 'deals' });
                } else if (tool === 'pipedrive_get_activities') {
                    result.push({ id: 'activities', title: 'Atividades e Histórico', icon: <ClipboardList size={13} />, content: event.summary, type: 'activities' });
                } else if (tool === 'whatsapp_get_messages' || tool === 'email_get_contact_history') {
                    result.push({
                        id: `comm_${tool}`,
                        title: tool === 'whatsapp_get_messages' ? 'Histórico WhatsApp' : 'Histórico E-mail',
                        icon: <MessageSquare size={13} />, content: event.summary, type: 'messages',
                    });
                } else if (tool === 'evaluate_prospects') {
                    result.push({ id: 'evaluation', title: 'Ranking de Decisores', icon: <Target size={13} />, content: event.summary, type: 'evaluation' });
                } else if (tool === 'generate_prospecting_plan') {
                    let planContent = detail;
                    if (event.data?.plan) planContent = event.data.plan;
                    else { try { const p = typeof event.content === 'string' ? JSON.parse(event.content) : event.content; if (p?.plan) planContent = p.plan; else if (p?.data?.plan) planContent = p.data.plan; } catch { /* ignore */ } }
                    result.push({ id: 'prospecting_plan', title: 'Plano de Prospecção (SPIN)', icon: <Target size={13} />, content: planContent, type: 'dossier' });
                }
            }
        }

        if (dbPlan) {
            const parts = dbPlan.split(' | [Dossiê]');
            const spinPlan = parts.length > 1 ? parts[0] : (!dbPlan.includes('[Dossiê]') ? dbPlan : '');
            const dossier  = parts.length > 1 ? '[Dossiê]' + parts[1] : (dbPlan.includes('[Dossiê]') ? dbPlan : '');

            if (spinPlan && !result.find(i => i.id === 'prospecting_plan')) {
                result.push({ id: 'prospecting_plan', title: 'Plano de Prospecção (SPIN)', icon: <Target size={13} />, content: spinPlan.trim(), type: 'dossier' });
            }
            if (dossier && !result.find(i => i.id === 'dossier_data')) {
                result.push({ id: 'dossier_data', title: 'Dossiê Pré-Abordagem', icon: <Target size={13} />, content: dossier.trim(), type: 'dossier' });
            }
        }

        const order = ['scope', 'dossier', 'evaluation', 'org', 'contacts', 'deals', 'activities', 'messages'];
        result.sort((a, b) => {
            const ia = order.indexOf(a.id === 'scope' ? 'scope' : a.type);
            const ib = order.indexOf(b.id === 'scope' ? 'scope' : b.type);
            return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
        });

        return result;
    }, [messages, orgId, orgName, dealId, dbPlan]);

    if (items.length === 0) return null;

    const toggleSection = (id: string) =>
        setOpenSections(prev => {
            const next = new Set(prev);
            next.has(id) ? next.delete(id) : next.add(id);
            return next;
        });

    // badges dos tipos únicos no header
    const uniqueTypes = [...new Set(items.map(i => i.type))];

    return (
        <div className={styles.contextAccordionContainer}>
            {/* ── HEADER ── */}
            <div className={styles.contextAccordionHeader} onClick={() => setIsOpen(!isOpen)}>
                <div className={styles.contextHeaderLeft}>
                    <span className={styles.contextHeaderTitle}>Contexto</span>
                </div>

                <div className={styles.contextHeaderRight}>
                    <span className={styles.contextItemCount}>{items.length}</span>

                    {dbPlan && (
                        <button
                            className={styles.deletePlanButton}
                            onClick={async (e) => {
                                e.stopPropagation();
                                if (window.confirm('Deseja realmente apagar o plano de prospecção desta empresa?')) {
                                    if (orgId) {
                                        try { await organizations.deleteProspectingPlan(orgId); setDbPlan(null); }
                                        catch (err) { console.error(err); alert('Erro ao apagar o plano de prospecção.'); }
                                    }
                                }
                            }}
                            title="Apagar plano de prospecção"
                        >
                            <Trash2 size={13} />
                        </button>
                    )}

                    <ChevronDown
                        size={14}
                        className={`${styles.contextChevron} ${isOpen ? styles.rotated : ''}`}
                    />
                </div>
            </div>

            {/* ── BODY ── */}
            {isOpen && (
                <div className={styles.contextAccordionBodyMarkdown}>
                    <div className={styles.contextAccordionScrollArea}>
                        {items.map((item) => {
                            const accent = TYPE_COLORS[item.type] ?? 'var(--sw-primary)';
                            const expanded = openSections.has(item.id);
                            return (
                                <div
                                    key={item.id}
                                    className={styles.contextSection}
                                    style={{ '--ctxAccent': accent } as React.CSSProperties}
                                >
                                    <button
                                        className={styles.contextSectionHeader}
                                        onClick={() => toggleSection(item.id)}
                                    >
                                        <span className={styles.contextSectionAccent} />
                                        <span className={styles.contextSectionIcon} style={{ color: accent }}>
                                            {item.icon}
                                        </span>
                                        <span className={styles.contextSectionTitle}>{item.title}</span>
                                        <ChevronDown
                                            size={12}
                                            className={`${styles.contextSectionChevron} ${expanded ? styles.rotated : ''}`}
                                        />
                                    </button>

                                    {expanded && (
                                        <div className={styles.contextSectionContent}>
                                            <ReactMarkdown>{item.content}</ReactMarkdown>
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}
        </div>
    );
};
