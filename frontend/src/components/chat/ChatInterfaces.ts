export interface Message {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: Date;
    sources?: number;
    thinkingTime?: string;
    selectedCompanies?: CompanyResult[];
    ui_module?: 'TaskList' | 'ContactGrid' | 'CompanyCard' | 'WhatsAppThread' | 'EmailThread' | 'AgentWorkflow' | null;
    data?: any;
    logs?: any[];
    pending_approvals?: ApprovalAction[];
    debug?: {
        intent?: any;
        data_scope?: string[];
        raw_context?: any;
        full_prompt?: string;
    };
    showDebug?: boolean;
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
}
