export interface HierarchyEmployee {
    id: string;
    name: string;
    role: string;
    department: string;
    company?: string;
    manager_id?: string;
    level: number;
    email?: string;
    linkedin?: string;
    location?: string;
}

export interface HierarchyResponse {
    company_name: string;
    identifier: string;
    employees: HierarchyEmployee[];
}
