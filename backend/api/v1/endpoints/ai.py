from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Dict, List
from services.external.groq_service import GroqService
from services.context_service import ContextService
from core.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
import re
import json

router = APIRouter()

class CompanyInfo(BaseModel):
    id: int
    name: str

class ChatMessage(BaseModel):
    message: str
    orgId: Optional[int] = None
    selectedCompanies: Optional[List[CompanyInfo]] = None
    context: Optional[str] = "hierarchy_analysis"

class ChatResponse(BaseModel):
    response: str

def _clean_response(text: str) -> str:
    """
    Remove markdown, code blocks e formata a resposta para exibição limpa.
    """
    if not text:
        return ""
    
    # Remove triple backticks de markdown (```json, ```python, ``` etc)
    text = re.sub(r'```[\w]*\n?', '', text)
    text = re.sub(r'```', '', text)
    
    # Remove backticks simples de código inline
    text = re.sub(r'`([^`]+)`', r'\1', text)
    
    # Remove markdown headers (#, ##, etc)
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
    
    # Remove bold markdown (**text**)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    
    # Remove italic markdown (*text* ou _text_)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    
    # Remove markdown links [text](url)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    
    # Limpa espaços em branco extras
    text = re.sub(r'\n\n+', '\n\n', text)
    text = text.strip()
    
    return text

def _format_context_for_prompt(context_dict: dict) -> str:
    """
    Formata contexto estruturado em texto legível para o Groq.
    Isso torna explícito qual é o dado disponível.
    """
    if not context_dict:
        return "NENHUM DADO INTERNO MAPEADO FOI ENCONTRADO"
    
    lines = ["═" * 60, "DADOS INTERNOS MAPEADOS:", "═" * 60]
    
    # Organização
    if "organization" in context_dict:
        org = context_dict["organization"]
        lines.append("\nORGANIZAÇÃO:")
        lines.append(f"  Nome: {org.get('name', 'N/A')}")
        lines.append(f"  CNPJ: {org.get('cnpj', 'N/A')}")
        lines.append(f"  Categoria: {org.get('category', 'Não especificada')}")
        lines.append(f"  Foco: {org.get('product_focus', 'Não especificado')}")
        lines.append(f"  Site: {org.get('domain', 'Não informado')}")
    
    # Estatísticas
    if "statistics" in context_dict:
        stats = context_dict["statistics"]
        lines.append("\nESTATÍSTICAS:")
        lines.append(f"  Total de funcionários mapeados: {stats.get('total_employees_mapped', 0)}")
        depts = stats.get('departments', [])
        if depts:
            lines.append(f"  Departamentos: {', '.join(depts)}")
        else:
            lines.append("  Departamentos: Não informados")
    
    # Decision Makers
    if "decision_makers" in context_dict:
        makers = context_dict["decision_makers"]
        if makers:
            lines.append("\nTOMADORES DE DECISÃO (por influência):")
            for i, maker in enumerate(makers[:10], 1):
                lines.append(f"  {i}. {maker.get('name', 'Desconhecido')} - {maker.get('role', 'Cargo desconhecido')} (Dept: {maker.get('department', 'N/A')} | Score: {maker.get('influence_score', 0)})")
        else:
            lines.append("\nTOMADORES DE DECISÃO: Nenhum encontrado nos dados mapeados")
    
    # Employees
    if "employees" in context_dict:
        emps = context_dict["employees"]
        if isinstance(emps, dict):
            lines.append("\nFUNCIONÁRIOS POR DEPARTAMENTO:")
            for dept, emp_list in emps.items():
                lines.append(f"  {dept}:")
                for emp in emp_list[:5]:
                    lines.append(f"    - {emp.get('name', 'Desconhecido')} ({emp.get('role', 'Cargo desconhecido')})")
                if len(emp_list) > 5:
                    lines.append(f"    ... e mais {len(emp_list) - 5}")
        elif isinstance(emps, list) and emps:
            lines.append("\nFUNCIONÁRIOS:")
            for emp in emps[:10]:
                lines.append(f"  - {emp.get('name', 'Desconhecido')} ({emp.get('role', 'Cargo')}) - {emp.get('department', 'Dept N/A')}")
            if len(emps) > 10:
                lines.append(f"  ... e mais {len(emps) - 10}")
        elif not emps:
            lines.append("\nFUNCIONÁRIOS: Nenhum funcionário mapeado para essa organização")
    
    # Contatos
    if "contacts" in context_dict:
        contacts = context_dict["contacts"]
        if contacts.get("contacts"):
            lines.append("\nCONTATOS COM WHATSAPP:")
            for contact in contacts.get("contacts", [])[:10]:
                status = "✓ ATIVO" if contact.get("whatsapp_active") else "✗ Não no WhatsApp"
                lines.append(f"  - {contact.get('name', 'Desconhecido')} ({contact.get('role', 'Cargo')})")
                lines.append(f"    Email: {contact.get('email', 'N/A')} | {status}")
        else:
            lines.append("\nCONTATOS: Nenhum contato mapeado")
    
    lines.append("\n" + "═" * 60)
    lines.append("FIM DOS DADOS")
    lines.append("═" * 60)
    
    return "\n".join(lines)


@router.post("/chat", response_model=ChatResponse)
async def chat_with_ai(
    payload: ChatMessage,
    session: AsyncSession = Depends(get_db)
):
    """
    Endpoint para chat com IA usando Groq com RAG (Retrieval Augmented Generation).
    
    Busca dados internos do banco e passa como contexto para a IA responder.
    
    Args:
        payload.message: Mensagem do usuário
        payload.orgId: ID da organização (para contexto)
        payload.context: Contexto da conversa (hierarchy_analysis, general, etc)
    
    Returns:
        response: Resposta da IA formatada e limpa com dados contextualizados
    """
    try:
        if not payload.message or not payload.message.strip():
            raise HTTPException(status_code=400, detail="Mensagem vazia")
        
        # 1. Extrair informações da pergunta
        org_id = payload.orgId
        intent = await ContextService.classify_question_intent(payload.message)
        
        # Prioridade: selectedCompanies > orgId > extrair da mensagem
        if payload.selectedCompanies and len(payload.selectedCompanies) > 0:
            # Usar a primeira empresa selecionada
            org_id = payload.selectedCompanies[0].id
            print(f"[AI Chat] Usando empresa selecionada: {payload.selectedCompanies[0].name} (ID: {org_id})")
        elif not org_id:
            # Tentar extrair nome de organização da mensagem
            org_name = await ContextService.extract_organization_name(payload.message)
            if org_name:
                org_data = await ContextService.fetch_organization_by_name(session, org_name)
                if org_data:
                    org_id = org_data.id
        
        # 2. Buscar contexto do banco se temos orgId
        internal_context = {}
        if org_id:
            internal_context = await ContextService.build_context_for_ai(session, org_id, intent)
        
        # 3. Montar o prompt com contexto
        # Se payload.context não for fornecido, usar o intent detectado automaticamente
        system_context_type = payload.context if payload.context and payload.context != "general" else intent
        system_context = _get_system_context(system_context_type)
        
        # Se temos contexto interno, adicionar como dados estruturados e legíveis para a IA
        context_prompt = ""
        if internal_context:
            formatted_context = _format_context_for_prompt(internal_context)
            context_prompt = f"\n\n{formatted_context}"
        
        full_prompt = f"{system_context}{context_prompt}\n\nPergunta do Usuário: {payload.message}"
        
        # 4. Usar GroqService para processar
        groq_service = GroqService()
        response = await groq_service.ask(full_prompt, json_mode=False)
        
        # 5. Validar e limpar resposta
        if not response:
            return ChatResponse(response="Desculpe, não consegui processar sua mensagem no momento.")
        
        # Se response for um dict (JSON), extrair o texto
        if isinstance(response, dict):
            # Se houver erro na resposta
            if "error" in response:
                return ChatResponse(response=f"Erro ao processar: {response.get('error', 'Erro desconhecido')}")
            # Se houver resposta estruturada
            response_text = response.get("response", response.get("text", str(response)))
        else:
            response_text = str(response)
        
        # Validar que temos uma resposta válida
        if not response_text or not isinstance(response_text, str):
            response_text = "Desculpe, não consegui gerar uma resposta adequada."
        
        # LIMPAR A RESPOSTA: remover markdown, code blocks, etc
        cleaned_response = _clean_response(response_text)
        
        return ChatResponse(response=cleaned_response)
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback_msg = traceback.format_exc()
        print(f"[AI Chat] Erro ao processar mensagem: {error_msg}")
        print(f"[AI Chat] Traceback:\n{traceback_msg}")
        raise HTTPException(status_code=500, detail=f"Erro ao processar mensagem: {error_msg}")

def _get_system_context(context: str) -> str:
    """Retorna o contexto do sistema baseado no tipo de conversa."""
    base_instructions = """BASE DE DADOS INTERNA:
Você tem acesso a dados mapeados internamente sobre organizações e seus funcionários.

🔴 REGRA CRÍTICA: Use APENAS os dados fornecidos entre "DADOS INTERNOS MAPEADOS" e "FIM DOS DADOS"
- NÃO invente nomes de pessoas, cargos ou departamentos
- NÃO assuma informações não fornecidas
- Se um dado não estiver na lista, diga claramente: "Não encontramos essas informações nos dados mapeados"
- Seja específico - cite APENAS nomes, cargos, departamentos reais que aparecem nos dados

FORMATO DE RESPOSTA:
- Texto plano bem estruturado
- SEM markdown, backticks ou code blocks
- Títulos em MAIÚSCULAS com dois-pontos
- Listas com • para itens
- Espaçamento claro entre sections

ESTRUTURA DOS DADOS FORNECIDOS:
Se há dados incompletos ou poucos registros, reporte isso honestamente ao usuário."""
    
    contexts = {
        "hierarchy_analysis": f"""{base_instructions}

Você é um assistente especializado em análise de hierarquias organizacionais e mapeamento B2B. 
Sua função é ajudar a entender estruturas organizacionais reais baseado em dados mapeados.

ANÁLISE COM DADOS REAIS:
- Use dados fornecidos para identificar tomadores de decisão (pelos cargos: Diretor, CEO, Sócio, Administrador)
- Reconheça departamentos reais que aparecem nos dados
- Aponte oportunidades baseadas APENAS na estrutura real encontrada
- Se os dados forem limitados, seja honesto: "Os dados mapeados mostram X registros, mas há limitações em..."

NUNCA invente executivos ou estrutura organizacional.""",
        
        "contacts": f"""{base_instructions}

Você é especialista em contatos e relacionamentos B2B. 

DADOS DE WHATSAPP E CONTATOS:
Quando contatos forem fornecidos com dados de WhatsApp:
- Priorize contatos com whatsapp_active=true (confirmados no WhatsApp)
- Forneça nome completo EXATO, cargo, departamento e email conforme nos dados
- Indique claramente quem está ativo no WhatsApp para comunicação direta
- Organize por departamento quando houver múltiplos contatos
- Se não houver contatos ativos em WhatsApp, esclareça: "Não encontramos contatos confirmados no WhatsApp"

REGRA: Use NOMES EXATOS dos dados fornecidos, não invente variações.""",
        
        "general": f"""{base_instructions}

Você é um assistente B2B profissional que analisa dados internos da empresa.
- Forneça respostas precisas baseadas nos dados que receber
- Se informações não estiverem disponíveis, diga explicitamente
- Seja conciso e objetivo""",
        
        "strategy": f"""{base_instructions}

Você é um estrategista B2B. Analise os dados internos para identificar:
- Mercados e oportunidades baseados em dados reais
- Padrões na estrutura organizacional encontrados
- Recomendações estratégicas fundamentadas nos dados

IMPORTANTE: Diferencie entre dados confirmados e especulação:
- "Encontramos..." = dados reais
- "Poderia haver..." = especulação (deixe claro o risco)""",
        
        "relationship": f"""{base_instructions}

Você é especialista em relacionamentos comerciais e networking B2B.
Com os dados internos, identifique:
- Conexões reais entre pessoas registradas nos dados
- Parceiros potenciais com base em estrutura real
- Oportunidades de colaboração confirmadas

NUNCA assuma relacionamentos que não estejam nos dados fornecidos."""
    }
    
    return contexts.get(context, contexts["general"])
    
    return contexts.get(context, contexts["general"])
