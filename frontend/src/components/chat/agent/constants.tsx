import React from 'react';
import {
    Network, Phone, Calendar, Clock, Layers, FileText,
    MessageSquare, Lightbulb, Package, ClipboardList, Box, Target,
} from 'lucide-react';
import { TaskCategory } from './types';

// ─── Ferramentas de escrita (efeito colateral real) ───────────────────────────

export const WRITE_TOOLS = new Set([
    'email_send', 'email_reply', 'whatsapp_send_message',
    'pipedrive_advance_deal', 'pipedrive_create_task',
    'pipedrive_update_task', 'pipedrive_create_person', 'pipedrive_create_note'
]);

// ─── Cores por ferramenta ─────────────────────────────────────────────────────

export const TOOL_COLORS: Record<string, string> = {
    whatsapp_get_messages: '#25d366',
    whatsapp_list_chats: '#25d366',
    whatsapp_send_message: '#25d366',
    pipedrive_get_org: '#f36e21',
    pipedrive_get_persons: '#f36e21',
    pipedrive_get_deals: '#f36e21',
    pipedrive_get_activities: '#f36e21',
    pipedrive_get_all_activities: '#f36e21',
    pipedrive_update_deal: '#f36e21',
    pipedrive_create_task: '#f36e21',
    pipedrive_update_task: '#f36e21',
    pipedrive_create_note: '#f36e21',
    pipedrive_create_person: '#f36e21',
    email_get_inbox: '#7a8bff',
    email_get_contact_history: '#7a8bff',
    email_send: '#7a8bff',
    email_reply: '#7a8bff',
    web_search: '#60a5fa',
    web_search_external: '#60a5fa',
    find_company_contact: '#60a5fa',
    evaluate_prospects: '#a78bfa',
    generate_dossier: '#a78bfa',
    prepare_live_coaching_session: '#3b82f6',
    open_ligacao_view: '#10b981',
    open_hierarchy_drawer: '#818cf8',
    suggest_next_actions: '#10b981',
};

// ─── Contexto de leitura: ferramentas que fazem parte da Fase 1 ───────────────

export const CONTEXT_TOOLS = new Set([
    'pipedrive_get_org', 'pipedrive_get_persons', 'pipedrive_get_deals',
    'pipedrive_get_activities', 'whatsapp_get_messages', 'email_get_contact_history',
]);

// ─── Categorias de tarefa ─────────────────────────────────────────────────────

export const detectTaskCategory = (label: string): TaskCategory => {
    const l = label.toLowerCase();
    if (/(encontrar|conseguir|buscar|mapear|pesquisar).*(contato|decisor)|decisor.*(real|certo)/.test(l)) return 'find_contact';
    if (/(ligar|ligação|chamada|telefonar|provocar|primeiro contato|call)/.test(l)) return 'call';
    if (/(reunião|meeting|agendar|marcar reunião|visita|reagendar|cold meet|ir pessoalmente)/.test(l)) return 'meeting';
    if (/(follow.?up|cobrar retorno|acompanhar|aguardar retorno)/.test(l)) return 'followup';
    if (/(apresentação|apresentacao|proposta comercial|linkb2b)/.test(l)) return 'presentation';
    if (/(orçamento|cotação|orcamento|cotacao|realizar orçamento|fazer cotação)/.test(l)) return 'quote';
    if (/(insight|insigth|mercado|tendência)/.test(l)) return 'insight';
    if (/(pedido|compra|programação de pedidos|cobrar pedido|colocar pedido)/.test(l)) return 'order';
    if (/(homologação|homologacao|confidencialidade|formulário|cadastro de fornecedor)/.test(l)) return 'homologation';
    if (/(amostra|levar amostra|retirar amostra)/.test(l)) return 'sample';
    if (/(linkedin|seguir no linkedin|conexão no linkedin|qualificar oportunidade|saneamento)/.test(l)) return 'strategic';
    if (/(email|e-mail|mensagem|whatsapp|escrever|enviar)/.test(l)) return 'message';
    return 'unknown';
};

export const CATEGORY_CONFIG: Record<TaskCategory, { icon: React.ReactNode; color: string; label: string; isManual?: boolean }> = {
    find_contact:  { icon: <Network size={14} />,        color: '#818cf8', label: 'Mapear Decisor' },
    call:          { icon: <Phone size={14} />,           color: '#3b82f6', label: 'Ligação' },
    meeting:       { icon: <Calendar size={14} />,        color: '#f59e0b', label: 'Reunião' },
    followup:      { icon: <Clock size={14} />,           color: '#10b981', label: 'Follow-up' },
    presentation:  { icon: <Layers size={14} />,          color: '#a855f7', label: 'Apresentação' },
    quote:         { icon: <FileText size={14} />,        color: '#06b6d4', label: 'Orçamento' },
    message:       { icon: <MessageSquare size={14} />,   color: '#7a8bff', label: 'Mensagem' },
    insight:       { icon: <Lightbulb size={14} />,       color: '#eab308', label: 'Insight' },
    order:         { icon: <Package size={14} />,         color: '#f97316', label: 'Pedido' },
    homologation:  { icon: <ClipboardList size={14} />,   color: '#14b8a6', label: 'Homologação' },
    sample:        { icon: <Box size={14} />,             color: '#8b5cf6', label: 'Amostra' },
    strategic:     { icon: <Target size={14} />,          color: '#ec4899', label: 'Estratégico', isManual: true },
    unknown:       { icon: <Clock size={14} />,           color: '#6b7280', label: 'Tarefa' },
};
