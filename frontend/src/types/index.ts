/**
 * Tipos compartilhados — superficie pública do client.
 * Reexporta tudo daqui para facilitar imports: `import { ... } from '@/types'`.
 */

export interface HierarchyEmployee {
  id: string;
  name: string;
  role: string;
  department: string;
  company?: string;
  manager_id?: string;
  level: number;
  email?: string;
  phone?: string;
  linkedin?: string;
  linkedin_url?: string;
  logo?: string;
  url?: string;
  location?: string;
  domain?: string;
  company_logo?: string;
  seniority?: number;
  bio?: string;
  education?: string;
  avatar?: string;
  profile_pic?: string;
  matching_score?: number;
  evidence?: string;
  headline?: string;
  temperature?: string | number;
  [key: string]: unknown;
}

export interface HierarchyResponse {
  company_name: string;
  identifier: string;
  employees: HierarchyEmployee[];
}

export interface OrganizationSummary {
  id: number | string;
  name: string;
  domain?: string | null;
  cnpj?: string | null;
  address?: string | null;
  local_id?: number;
  logo?: string | null;
  linkedin?: string | null;
  category?: string | null;
  product_focus?: string | null;
  employee_count?: number;
  employee_pics?: string[];
  stage_name?: string;
  stage_order_nr?: number;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    request_id?: string | null;
    details?: unknown;
  };
}

export interface ChatHistoryEntry {
  role: 'user' | 'assistant' | 'system';
  content: string;
  data?: unknown;
  logs?: unknown;
  debug?: unknown;
}

export interface ChatPayload {
  message: string;
  history?: ChatHistoryEntry[];
  orgId?: number | null;
  selectedCompanies?: Array<{
    id?: number;
    name?: string;
    domain?: string | null;
    [k: string]: unknown;
  }>;
  context?: string | Record<string, unknown> | null;
  /** Provider do LLM para a volta. */
  model?: 'gemini' | 'groq' | 'claude' | 'cerebras' | 'deepseek' | 'sambanova' | 'ollama' | string;
}

export interface SearchResultItem {
  id?: number | string;
  name?: string;
  type?: 'whatsapp' | 'email' | 'empresa' | 'cnpj' | 'lead' | string;
  [k: string]: unknown;
}

export interface UniversalSearchResponse {
  results: SearchResultItem[];
  [k: string]: unknown;
}

export interface ChatResponse {
  response?: string;
  ui_module?: string;
  data?: Record<string, unknown>;
  pipedrive_cooldown?: number;
  [k: string]: unknown;
}

export interface JobStreamEvent {
  type: 'log' | 'final' | 'pending_approvals' | string;
  content?: string | Record<string, unknown>;
  response?: string;
  data?: Record<string, unknown>;
  actions?: unknown[];
  pipedrive_cooldown?: number;
  [k: string]: unknown;
}
