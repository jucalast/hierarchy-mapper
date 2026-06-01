import React, { useState, useMemo } from 'react';
import { 
    ChevronDown, Building2, Users, 
    Briefcase, ClipboardList, MessageSquare, FileText,
    Target, LayoutList
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { GlassContainer } from './GlassContainer';
import styles from './ChatPanel.module.css';

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

export const ConversationContextAccordion: React.FC<ConversationContextAccordionProps> = ({ 
    messages, 
    orgId, 
    orgName, 
    dealId 
}) => {
    const [isOpen, setIsOpen] = useState(false);

    const fullMarkdownContext = useMemo(() => {
        const items: ContextItem[] = [];
        const seenTools = new Set<string>();

        // 1. Adiciona contexto de escopo inicial se disponível
        if (orgId || orgName || dealId) {
            let scopeContent = "";
            if (orgName) scopeContent += `- **Empresa Focus**: ${orgName}\n`;
            if (orgId) scopeContent += `- **Pipedrive Org ID**: ${orgId}\n`;
            if (dealId) scopeContent += `- **Pipedrive Deal ID**: ${dealId}\n`;
            
            items.push({
                id: 'scope',
                title: 'Escopo da Sessão',
                icon: <Target size={14} />,
                content: scopeContent,
                type: 'evaluation' // Reusing evaluation slot for scope
            });
        }

        // Percorre as mensagens de trás para frente para pegar o contexto mais recente
        for (let i = messages.length - 1; i >= 0; i--) {
            const msg = messages[i];
            if (!msg.isAgent || !msg.agentEvents) continue;

            for (const event of msg.agentEvents) {
                if (event.type !== 'tool_result' || !event.tool || !event.summary || !event.ok) continue;
                
                const tool = event.tool;
                if (seenTools.has(tool)) continue;
                seenTools.add(tool);

                // Prioriza o conteúdo completo (response/content) sobre o resumo (summary)
                const detailedContent = event.response || event.content || event.summary;

                if (tool === 'generate_dossier' || tool === 'deep_company_investigation') {
                    items.push({
                        id: 'dossier',
                        title: 'Dossiê Estratégico',
                        icon: <FileText size={14} />,
                        content: detailedContent,
                        type: 'dossier'
                    });
                } else if (tool === 'pipedrive_get_org') {
                    items.push({
                        id: 'org',
                        title: 'Dados da Empresa (CRM)',
                        icon: <Building2 size={14} />,
                        content: detailedContent,
                        type: 'org'
                    });
                } else if (tool === 'pipedrive_get_persons') {
                    items.push({
                        id: 'contacts',
                        title: 'Contatos Identificados',
                        icon: <Users size={14} />,
                        content: event.summary,
                        type: 'contacts'
                    });
                } else if (tool === 'pipedrive_get_deals') {
                    items.push({
                        id: 'deals',
                        title: 'Negócios em Aberto',
                        icon: <Briefcase size={14} />,
                        content: event.summary,
                        type: 'deals'
                    });
                } else if (tool === 'pipedrive_get_activities') {
                    items.push({
                        id: 'activities',
                        title: 'Atividades e Histórico',
                        icon: <ClipboardList size={14} />,
                        content: event.summary,
                        type: 'activities'
                    });
                } else if (tool === 'whatsapp_get_messages' || tool === 'email_get_contact_history') {
                    items.push({
                        id: `comm_${tool}`,
                        title: tool === 'whatsapp_get_messages' ? 'Histórico WhatsApp' : 'Histórico E-mail',
                        icon: <MessageSquare size={14} />,
                        content: event.summary,
                        type: 'messages'
                    });
                } else if (tool === 'evaluate_prospects') {
                    items.push({
                        id: 'evaluation',
                        title: 'Ranking de Decisores',
                        icon: <Target size={14} />,
                        content: event.summary,
                        type: 'evaluation'
                    });
                }
            }
        }

        if (items.length === 0) return null;

        // Ordenação preferida para o Markdown
        const order = ['scope', 'dossier', 'evaluation', 'org', 'contacts', 'deals', 'activities', 'messages'];
        items.sort((a, b) => {
            const idxA = order.indexOf(a.id === 'scope' ? 'scope' : a.type);
            const idxB = order.indexOf(b.id === 'scope' ? 'scope' : b.type);
            return (idxA === -1 ? 99 : idxA) - (idxB === -1 ? 99 : idxB);
        });

        // Constrói o Markdown consolidado
        let md = "";
        items.forEach(item => {
            md += `### ${item.title}\n${item.content}\n\n---\n\n`;
        });
        
        return md;
    }, [messages, orgId, orgName, dealId]);

    if (!fullMarkdownContext) return null;

    return (
        <div className={styles.contextAccordionContainer}>
            <div 
                className={styles.contextAccordionHeader} 
                onClick={() => setIsOpen(!isOpen)}
            >
                <div className={styles.contextHeaderLeft}>
                    <span className={styles.contextHeaderTitle}>Contexto</span>
                </div>

                <div className={styles.contextHeaderRight}>
                    <ChevronDown 
                        size={16} 
                        className={`${styles.arrow} ${isOpen ? styles.rotated : ''}`} 
                    />
                </div>
            </div>

            {isOpen && (
                <div className={styles.contextAccordionBodyMarkdown}>
                    <div className={styles.contextAccordionScrollArea}>
                        <ReactMarkdown>{fullMarkdownContext}</ReactMarkdown>
                    </div>
                </div>
            )}
        </div>
    );
};
