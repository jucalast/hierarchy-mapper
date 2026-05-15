import { AIModel } from './components/ui/ModelSelector';

export interface SuggestedAction {
    label: string;
    prompt: string;
    icon?: string;
    razao?: string;
    categoria?: string;
}

export interface CompanyResult {
    id: number | string;
    name: string;
    type?: 'organization' | 'whatsapp' | 'email';
    domain?: string;
    logo_url?: string;
    phone?: string;
    email?: string;
}

export interface ApprovalAction {
    action_id: string;
    action_type: string;
    channel: string;
    contact_name: string;
    contact_phone?: string;
    contact_email?: string;
    subject?: string;
    message_preview: string;
    description: string;
    is_reply?: boolean;
    original_subject?: string;
    email_entry_id?: string;
}

export interface Message {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: Date;
    sources?: number;
    thinkingTime?: string;
    selectedCompanies?: CompanyResult[];
    ui_module?: 'TaskList' | 'ContactGrid' | 'CompanyCard' | 'WhatsAppThread' | 'EmailThread' | 'AgentWorkflow' | 'DealStatus' | null;
    data?: any;
    logs?: any[];
    pending_approvals?: ApprovalAction[];
    suggested_actions?: SuggestedAction[];
    debug?: {
        intent?: any;
        data_scope?: string[];
        raw_context?: any;
        full_prompt?: string;
    };
    showDebug?: boolean;
    isV2?: boolean;
    v2Events?: V2Event[];
    v2Streaming?: boolean;
    v2ConfirmedActions?: Record<string, boolean>;
}

export interface V2Event {
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
    actions?: SuggestedAction[];
    response?: string;
    model?: string;
    wait_sec?: number;
    reason?: string;
    estimated_tokens?: number;
    limit?: number;
    org_name?: string;
    org_id?: number | null;
    deal_id?: number | null;
    activity_id?: number | null;
    pre_task_id?: number | null;
    error?: string;
}
