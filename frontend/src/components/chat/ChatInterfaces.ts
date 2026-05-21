export interface SuggestedAction {
    label: string;
    prompt: string;
    icon?: string;
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
    isAgent?: boolean;
    agentEvents?: any[];
    agentStreaming?: boolean;
    agentConfirmedActions?: Record<string, boolean>;
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
