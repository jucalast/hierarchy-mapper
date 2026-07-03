import { AIModel } from '../components/ModelSelector';

// ─── Eventos do stream do agente ──────────────────────────────────────────────

export interface AgentEvent {
    type: 'thinking' | 'tool_call' | 'tool_result' | 'confirmation_required' | 'final' | 'error' | 'context_saved' | 'rate_wait' | 'context_overflow' | 'suggested_actions' | 'hierarchy_mapping_required';
    content?: string;
    call_id?: string;
    tool_use_id?: string;
    tool_name?: string;
    tool?: string;
    args?: Record<string, any>;
    label?: string;
    summary?: string;
    ok?: boolean;
    action_id?: string;
    preview?: string;
    actions?: Array<{ label: string; prompt: string; razao?: string; categoria?: string }>;
    response?: string;
    model?: string;
    wait_sec?: number;
    reason?: string;
    estimated_tokens?: number;
    limit?: number;
    // hierarchy_mapping_required
    org_name?: string;
    org_id?: number | null;
    deal_id?: number | null;
    activity_id?: number | null;
    pre_task_id?: number | null;
    error?: string;
    data?: any;
    options?: any[];
    plan?: string;
    result?: any;
    /** tool_result: true quando o "erro" é uma confirmação recusada pelo usuário, não uma falha real da tool. */
    cancelled?: boolean;
    /** confirmation_required (email): destinatário resolvido para exibição no card. */
    to?: string;
    /** confirmation_required (email): cópias automáticas (compras@/suprimentos@) resolvidas para exibição no card. */
    cc?: string[];
    /** confirmation_required: marcado no front quando o envio aprovado falhou — mantém o card com botão "Tentar novamente". */
    send_failed?: boolean;
}

// ─── Mapeamento de hierarquia ─────────────────────────────────────────────────

export type MappingStatus = 'waiting' | 'scanning' | 'done';

export interface MappedContact {
    name: string;
    role: string;
    email?: string;
    phone?: string;
    department?: string;
    temperature?: string;
    level?: number;
    decision_maker?: boolean;
}

// ─── Tarefas sugeridas ────────────────────────────────────────────────────────

export type TaskStatus = 'pending' | 'streaming' | 'awaiting_confirm' | 'awaiting_mapping' | 'done' | 'rejected' | 'error' | 'cancelled';

export type TaskCategory =
    | 'find_contact' | 'call' | 'meeting' | 'followup'
    | 'presentation' | 'quote' | 'message' | 'insight'
    | 'order' | 'homologation' | 'sample' | 'strategic' | 'unknown';

// ─── Props do componente principal ────────────────────────────────────────────

export interface AgentMessageProps {
    messageId?: string;
    events: AgentEvent[];
    isStreaming?: boolean;
    onConfirm?: (action_id: string, approved: boolean, file?: File) => void;
    confirmedActions?: Record<string, boolean>;
    onRegenerate?: () => void;
    onAction?: (prompt: string) => void;
    // Para streaming inline das tarefas sugeridas
    streamV2Url?: string;
    confirmV2Url?: string;
    orgId?: number | null;
    selectedOrgName?: string | null;
    threadId?: string;
    approvedSuggestedActions?: Record<string, TaskStatus>;
    onApproveSuggestedAction?: (action: { label: string; prompt: string }, index: number, parentMessageId?: string) => void;
    onRetrySuggestedAction?: (action: { label: string; prompt: string }, index: number, parentMessageId?: string) => void;
    onHierarchyMappingDone?: (contacts: any[], event?: AgentEvent) => void;
    model: AIModel;
    onOpenTaskConsole?: (action: any, index: number, parentMessageId?: string) => void;
    onToggleBatch?: (action: { label: string; prompt: string; categoria?: string }, index: number, parentMessageId?: string) => void;
    batchQueue?: Array<{ messageId: string; actionIndex: number; action: any }>;
}
