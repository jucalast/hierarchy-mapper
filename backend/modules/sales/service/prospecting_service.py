"""
Backend service to generate and maintain Prospecting Plans (SPIN Selling).
"""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models import Organization, Product, BusinessProfile, Employee
from core.llm.router import ask_llm, LLMTier
from core.observability.logging_config import get_logger

log = get_logger(__name__)

async def build_spin_prospecting_plan(org_id: int, db: AsyncSession) -> Optional[str]:
    """
    Generates a SPIN Selling Prospecting Plan for an Organization.
    Fetches the organization, top employees, products and business profile.
    Saves the output to org.prospecting_context.
    """
    stmt_org = select(Organization).where((Organization.pipedrive_id == org_id) | (Organization.id == org_id))
    org = (await db.execute(stmt_org)).scalar_one_or_none()
    
    if not org:
        log.warning("prospecting_plan.org_not_found", org_id=org_id)
        return None

    # Fetch top contacts (ignore reprovados)
    stmt_emp = select(Employee).where(
        Employee.organization_id == org.id,
        Employee.role.not_ilike("%reprovado%"),
        Employee.department.not_ilike("%reprovado%")
    ).order_by(Employee.level.asc()).limit(15)
    
    employees = (await db.execute(stmt_emp)).scalars().all()

    stmt_bp = select(BusinessProfile).limit(1)
    bp = (await db.execute(stmt_bp)).scalar_one_or_none()
    
    stmt_prod = select(Product)
    products = (await db.execute(stmt_prod)).scalars().all()

    # Build context string
    contacts_str = "\n".join([f"- {e.name} ({e.role} - {e.department})" for e in employees if e.name])
    products_str = "\n".join([f"- {p.name}: {p.description} (Use Cases: {p.use_cases})" for p in products])
    
    bp_context = ""
    if bp:
        bp_context = f"Segment: {bp.segment}\nDifferentials: {bp.differentials}\nValue Propositions: {bp.value_propositions}\nMethodology: {bp.methodology}"

    prompt = f"""
Você é um Estrategista de Vendas B2B Master, especialista na metodologia SPIN Selling e Challenger Sale.

OBJETIVO:
Criar um Plano de Prospecção estratégico altamente detalhado para a empresa alvo. Este plano será o guia definitivo para todas as interações do nosso agente de vendas (e-mails, cold calls, WhatsApp).

### DADOS DA EMPRESA ALVO:
- Nome: {org.name}
- Categoria/Foco: {org.category} / {org.product_focus}
- Domínio: {org.domain}
- Descrição atual: {org.description or "Não informada"}

### CONTEXTO ANTERIOR (Mantenha e integre se relevante):
{org.prospecting_context or "Nenhum"}

### DECISORES E INFLUENCIADORES MAPEADOS:
{contacts_str or "Nenhum mapeado até o momento."}

### NOSSO PERFIL DE NEGÓCIO:
{bp_context or "Nenhum perfil de negócio cadastrado."}

### NOSSOS PRODUTOS (O que podemos vender):
{products_str or "Nenhum produto cadastrado."}

INSTRUÇÕES PARA O PLANO (Formato Markdown estrito, sem metadados extras):
1. **Resumo Executivo:** Qual é o ângulo de ataque para essa empresa?
2. **Matriz SPIN (Situação, Problema, Implicação, Necessidade de Solução):**
   - Elabore perguntas e hipóteses para cada etapa do SPIN focadas na realidade desta empresa e como nossos produtos resolvem.
3. **Mapeamento de Abordagem por Cargo:**
   - Como abordar cada decisor listado acima? Qual gatilho usar para cada um?
4. **Objeções Previstas e Contorno:**
   - Liste as 2 principais objeções que eles podem dar e como rebatê-las.
5. **Call-to-Action (Próximo Passo):**
   - Qual a ação imediata sugerida para iniciar a prospecção?
"""

    log.info("prospecting_plan.generating", org_id=org.id, org_name=org.name)
    
    # Run LLM
    result = await ask_llm(
        prompt=prompt,
        system="Você é um especialista em vendas B2B e estruturação de prospecção. Responda apenas com o Markdown do plano, sem introduções.",
        tier=LLMTier.SMART,
        temperature=0.3
    )

    if not result or not result.text:
        log.error("prospecting_plan.llm_empty_response", org_id=org.id)
        return None

    # Save to Org
    org.prospecting_context = result.text.strip()
    await db.commit()
    
    log.info("prospecting_plan.generated_and_saved", org_id=org.id)
    return org.prospecting_context
