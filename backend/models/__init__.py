"""
models
======
Ponto único de importação para todos os modelos SQLAlchemy do sistema.

Domínios disponíveis:
    conversation  → ConversationThread, ConversationMessage, ActivityLog
    crm           → Integration (Pipedrive, WhatsApp, Outlook)
    organization  → Organization, Tenant
    people        → Employee, ProspectSession, ProspectLead
    hierarchy     → HierarchyConfig
    system        → SystemSetting, User, BusinessProfile, Product,
                    ReferenceClient, ICPConfig, ICPScoreRule

Uso:
    from models import Organization, Employee, User
"""
from models.conversation import *
from models.crm import *
from models.organization import *
from models.people import *
from models.hierarchy import *
from models.system import *
