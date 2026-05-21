"""
api.v1.schemas
==============
Schemas Pydantic compartilhados entre routers e o modulo hierarchy.

Inclui schemas para o scanner B2B (EmployeeNode, HierarchyResponse,
ConfirmEnrichRequest) e configuracao do Tenant (BusinessProfileSchema,
ICPConfigSchema, HierarchyConfigSchema).

Utilitario: clean_cnpj(val) -> str  -- extrai apenas digitos do CNPJ
"""
from pydantic import BaseModel
from typing import List, Optional, Any
import re

def clean_cnpj(val: str) -> str:
    """Extrai apenas dígitos do CNPJ para APIs e Banco."""
    if not val: return ""
    return re.sub(r'\D', '', val)

class EmployeeNode(BaseModel):
    id: str
    name: str
    role: str
    department: str
    company: Optional[str] = None
    manager_id: Optional[str] = None
    level: int = 5
    email: Optional[str] = None
    linkedin: Optional[str] = None
    url: Optional[str] = None
    temperature: Optional[str] = None
    education: Optional[str] = None
    location: Optional[str] = None
    connections: Optional[str] = None
    highlights: Optional[str] = None
    observations: Optional[str] = None

class HierarchyResponse(BaseModel):
    company_name: str
    identifier: str
    employees: List[EmployeeNode]

class ConfirmEnrichRequest(BaseModel):
    name: str
    cnpj: Optional[str] = None
    domain: Optional[str] = None
    address: Optional[str] = None
    pipedrive_id: Optional[int] = None
    linkedin_url: Optional[str] = None
    logo_url: Optional[str] = None
    partners: Optional[List[dict]] = None

class CandidateActionRequest(BaseModel):
    employee_id: str
    action: str # 'approve' or 'reject'

# --- SaaS / Settings Schemas ---

class ProductSchema(BaseModel):
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    use_cases: Optional[List[str]] = None

class ReferenceClientSchema(BaseModel):
    id: Optional[str] = None
    name: str
    segment: Optional[str] = None
    pain_solved: Optional[str] = None

class BusinessProfileSchema(BaseModel):
    segment: Optional[str] = None
    differentials: Optional[List[str]] = None
    methodology: Optional[str] = None
    seller_name: Optional[str] = None
    seller_role: Optional[str] = None
    value_propositions: Optional[dict] = None

class ICPRuleSchema(BaseModel):
    rule_type: str
    value_pattern: str
    weight_score: int
    reason: str

class ICPConfigSchema(BaseModel):
    industries_target: Optional[List[str]] = None
    company_size_target: Optional[List[str]] = None
    decision_makers: Optional[List[str]] = None
    disqualifiers: Optional[List[str]] = None
    pain_points: Optional[List[str]] = None
    score_rules: Optional[List[ICPRuleSchema]] = None

class HierarchyConfigSchema(BaseModel):
    department_focus: str
    forbidden_keywords: Optional[dict] = None
    whitelist_keywords: Optional[Any] = None
    seniority_rules: Optional[dict] = None
    department_mapping_rules: Optional[dict] = None
