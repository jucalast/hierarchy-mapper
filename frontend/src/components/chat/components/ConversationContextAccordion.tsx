import React, { useState, useMemo, useEffect, useRef, useLayoutEffect } from 'react';
import { ChevronDown, Trash2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import styles from '../styles/ChatPanel.module.css';
import { organizations } from '@/services/api';
import { ConfirmModal } from '../../ui/ConfirmModal';
import { Dropdown } from '../../ui/Dropdown';

interface ContextItem {
    id: string;
    title: string;
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
    const [dbPlan, setDbPlan] = useState<string | null>(null);
    const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
    const containerRef = useRef<HTMLDivElement>(null);
    const [bodyHeight, setBodyHeight] = useState<number | null>(null);

    // A altura fixa do dropdown precisa ser calculada em runtime: o espaço real
    // disponível abaixo do header varia com abas/headers dinâmicos do painel, então
    // um valor fixo em vh cortava conteúdo sem oferecer scroll de verdade.
    // O corpo agora fica colado no header (sem gap no topo) pra formar uma caixa
    // única, como o console do ChatInput — só sobra uma folga no fundo.
    useLayoutEffect(() => {
        if (!isOpen) return;

        const BODY_TOP_GAP = 0;
        const BODY_BOTTOM_GAP = 8;

        const measure = () => {
            const headerEl = containerRef.current;
            const panelEl = headerEl?.closest('[data-chat-panel-root]') as HTMLElement | null;
            if (!headerEl || !panelEl) return;
            const headerRect = headerEl.getBoundingClientRect();
            const panelRect = panelEl.getBoundingClientRect();
            setBodyHeight(Math.max(0, panelRect.bottom - headerRect.bottom - BODY_TOP_GAP - BODY_BOTTOM_GAP));
        };

        measure();

        const panelEl = containerRef.current?.closest('[data-chat-panel-root]') as HTMLElement | null;
        const observer = new ResizeObserver(measure);
        if (containerRef.current) observer.observe(containerRef.current);
        if (panelEl) observer.observe(panelEl);
        window.addEventListener('resize', measure);

        return () => {
            observer.disconnect();
            window.removeEventListener('resize', measure);
        };
    }, [isOpen]);

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
            result.push({ id: 'scope', title: 'Escopo da Sessão', content: scopeContent, type: 'evaluation' });
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
                    result.push({ id: 'dossier', title: 'Dossiê Estratégico', content: detail, type: 'dossier' });
                } else if (tool === 'pipedrive_get_org') {
                    result.push({ id: 'org', title: 'Dados da Empresa (CRM)', content: detail, type: 'org' });
                } else if (tool === 'pipedrive_get_persons') {
                    result.push({ id: 'contacts', title: 'Contatos Identificados', content: event.summary, type: 'contacts' });
                } else if (tool === 'pipedrive_get_deals') {
                    result.push({ id: 'deals', title: 'Negócios em Aberto', content: event.summary, type: 'deals' });
                } else if (tool === 'pipedrive_get_activities') {
                    result.push({ id: 'activities', title: 'Atividades e Histórico', content: event.summary, type: 'activities' });
                } else if (tool === 'whatsapp_get_messages' || tool === 'email_get_contact_history') {
                    result.push({
                        id: `comm_${tool}`,
                        title: tool === 'whatsapp_get_messages' ? 'Histórico WhatsApp' : 'Histórico E-mail',
                        content: event.summary, type: 'messages',
                    });
                } else if (tool === 'evaluate_prospects') {
                    result.push({ id: 'evaluation', title: 'Ranking de Decisores', content: event.summary, type: 'evaluation' });
                } else if (tool === 'generate_prospecting_plan') {
                    let planContent = detail;
                    if (event.data?.plan) planContent = event.data.plan;
                    else { try { const p = typeof event.content === 'string' ? JSON.parse(event.content) : event.content; if (p?.plan) planContent = p.plan; else if (p?.data?.plan) planContent = p.data.plan; } catch { /* ignore */ } }
                    result.push({ id: 'prospecting_plan', title: 'Plano de Prospecção (SPIN)', content: planContent, type: 'dossier' });
                }
            }
        }

        if (dbPlan) {
            const parts = dbPlan.split(' | [Dossiê]');
            const spinPlan = parts.length > 1 ? parts[0] : (!dbPlan.includes('[Dossiê]') ? dbPlan : '');
            const dossier  = parts.length > 1 ? '[Dossiê]' + parts[1] : (dbPlan.includes('[Dossiê]') ? dbPlan : '');

            if (spinPlan && !result.find(i => i.id === 'prospecting_plan')) {
                result.push({ id: 'prospecting_plan', title: 'Plano de Prospecção (SPIN)', content: spinPlan.trim(), type: 'dossier' });
            }
            if (dossier && !result.find(i => i.id === 'dossier_data')) {
                result.push({ id: 'dossier_data', title: 'Dossiê Pré-Abordagem', content: dossier.trim(), type: 'dossier' });
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

    const handleDeletePlan = async () => {
        setShowDeleteConfirm(false);
        if (!orgId) return;
        try {
            await organizations.deleteProspectingPlan(orgId);
            setDbPlan(null);
        } catch (err) {
            console.error(err);
            alert('Erro ao apagar o plano de prospecção.');
        }
    };

    return (
        <div
            className={`${styles.contextAccordionContainer} ${isOpen ? styles.contextAccordionContainerOpen : ''}`}
            ref={containerRef}
        >
            {/* ── HEADER ── */}
            <div className={styles.contextAccordionHeader} onClick={() => setIsOpen(!isOpen)}>
                <div className={styles.contextHeaderLeft}>
                    <span className={styles.contextHeaderTitle}>Contexto</span>
                </div>

                <div className={styles.contextHeaderRight}>
                    {dbPlan && (
                        <div onClick={(e) => e.stopPropagation()}>
                            <Dropdown
                                items={[{
                                    label: 'Apagar plano de prospecção',
                                    icon: <Trash2 size={12} />,
                                    danger: true,
                                    onClick: () => setShowDeleteConfirm(true),
                                }]}
                                iconType="horizontal"
                                align="right"
                                iconSize={13}
                                title="Mais opções"
                                triggerClassName={styles.contextDropdownTrigger}
                            />
                        </div>
                    )}

                    <ChevronDown
                        size={14}
                        className={`${styles.contextChevron} ${isOpen ? styles.rotated : ''}`}
                    />
                </div>
            </div>

            {/* ── BODY ── */}
            {isOpen && (
                <div
                    className={styles.contextAccordionBodyMarkdown}
                    style={bodyHeight != null ? { height: `${bodyHeight}px` } : undefined}
                >
                    <div className={styles.contextAccordionScrollArea}>
                        {items.map((item) => {
                            const accent = TYPE_COLORS[item.type] ?? 'var(--sw-primary)';
                            return (
                                <div
                                    key={item.id}
                                    className={styles.contextSection}
                                    style={{ '--ctxAccent': accent } as React.CSSProperties}
                                >
                                    <div className={styles.contextSectionHeader}>
                                        <span className={styles.contextSectionAccent} />
                                        <span className={styles.contextSectionTitle}>{item.title}</span>
                                    </div>

                                    <div className={styles.contextSectionContent}>
                                        <ReactMarkdown>{item.content}</ReactMarkdown>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}

            <ConfirmModal
                isOpen={showDeleteConfirm}
                title="Apagar plano de prospecção"
                message="Deseja realmente apagar o plano de prospecção desta empresa? Esta ação não pode ser desfeita."
                confirmLabel="Apagar"
                onCancel={() => setShowDeleteConfirm(false)}
                onConfirm={handleDeletePlan}
                contained
            />
        </div>
    );
};
