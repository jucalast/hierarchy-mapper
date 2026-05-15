export type ActiveTab =
    | 'llm'
    | 'profile'
    | 'products'
    | 'references'
    | 'value_props'
    | 'icp'
    | 'hierarchy'
    | 'integrations';

export interface QuotaModelDetail {
    limit: number;
    remaining: number;
    used: number;
    pct: number;
    tokens_limit?: number;
    tokens_remaining?: number;
    tokens_pct?: number;
    status: string;
    updated_at: number;
}

export type QuotasResponse = Record<string, Record<string, QuotaModelDetail>>;

export interface Product {
    name: string;
    description: string;
    use_cases: string[];
}

export interface ReferenceClient {
    name: string;
    segment: string;
}
