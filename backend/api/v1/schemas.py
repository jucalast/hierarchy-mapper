from pydantic import BaseModel
from typing import List, Optional
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
