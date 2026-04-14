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
    
    # Remove JSON objects {}
    text = re.sub(r'\{[^{}]*\}', '', text)
    
    # Limpa espaços em branco extras
    text = re.sub(r'\n\n+', '\n\n', text)
    text = text.strip()
    
    return text

def _format_context_for_prompt(context_dict: dict) -> str:
    """
    Formata contexto em texto legível, sem JSON.
    Inclui APENAS dados que estão disponíveis no dict.
    """
    if not context_dict:
        return ""
    
    lines = ["\n--- INÍCIO DOS DADOS INTERNOS MAPEADOS DO SISTEMA ---"]
    
    # Organização (sempre incluir)
    if "organization" in context_dict:
        org = context_dict["organization"]
        if org and isinstance(org, dict):
            if org.get('name'):
                lines.append(f"Empresa: {org.get('name')}")
            if org.get('cnpj'):
                lines.append(f"CNPJ: {org.get('cnpj')}")
            if org.get('domain'):
                lines.append(f"Site/Domínio: {org.get('domain')}")
            if org.get('industry'):
                lines.append(f"Indústria: {org.get('industry')}")
    
    # Decision Makers
    if "decision_makers" in context_dict:
        makers_data = context_dict.get("decision_makers")
        makers = makers_data if isinstance(makers_data, list) else makers_data.get("decision_makers", []) if isinstance(makers_data, dict) else []
        if makers:
            lines.append("\nTOMADORES DE DECISÃO MAPEADOS:")
            for maker in makers[:15]:
                if isinstance(maker, dict):
                    name = maker.get('name', 'Desconhecido')
                    role = maker.get('role', 'Cargo não informado')
                    dept = maker.get('department', 'Departamento não informado')
                    lines.append(f"- {name} ({role} de {dept})")
    
    # Employees by Department
    if "employees_by_dept" in context_dict:
        emps = context_dict["employees_by_dept"]
        if emps and isinstance(emps, dict) and emps.get("by_department"):
            lines.append("\nFUNCIONÁRIOS MAPEADOS:")
            for dept, emp_list in list(emps.get("by_department", {}).items())[:10]:
                lines.append(f"\nEm {dept}:")
                for emp in emp_list[:5]:
                    if isinstance(emp, dict):
                        lines.append(f"- {emp.get('name', 'Desconhecido')} ({emp.get('role', 'S/C')})")
    
    # Estatísticas
    if "statistics" in context_dict and ("decision_makers" in context_dict or "employees_by_dept" in context_dict):
        stats = context_dict["statistics"]
        if isinstance(stats, dict):
            total_emp = stats.get('total_employees', stats.get('total_employees_mapped', 0))
            if total_emp > 0:
                lines.append(f"\nTotal de funcionários guardados no banco de dados para esta empresa: {total_emp}")
    
    if len(lines) == 1:
        return ""
        
    lines.append("--- FIM DOS DADOS INTERNOS MAPEADOS ---")
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
            try:
                # Sempre buscar apenas informações organizacionais básicas (sem estatísticas de departamentos)
                basic_context = await ContextService.fetch_organization_overview(session, org_id)
                org_data = basic_context.get("organization", {})
                
                # Iniciar com apenas organização (sem departamentos, sem estatísticas)
                internal_context = {
                    "organization": {
                        "name": org_data.get("name") if org_data else None,
                        "cnpj": org_data.get("cnpj") if org_data else None,
                        "domain": org_data.get("domain") if org_data else None
                    }
                }
                print(f"[AI Chat] Contexto inicial: {internal_context}")
                
                # Apenas buscar dados detalhados se o usuário perguntou sobre eles
                message_lower = payload.message.lower()
                if any(word in message_lower for word in ['funcionário', 'employee', 'contato', 'contact', 'pessoas', 'people', 'quem', 'nome', 'nomes', 'executivo', 'diretor', 'ceo', 'manager', 'gerente', 'departamento', 'responsável', 'chefe', 'estrutura']):
                    print(f"[AI Chat] Usuário perguntou sobre funcionários/estrutura, buscando dados completos...")
                    # Buscar informações completas quando solicitado
                    if org_data:
                        internal_context["organization"] = org_data
                    
                    # Buscar decision makers
                    try:
                        decision_makers_context = await ContextService.fetch_decision_makers(session, org_id)
                        internal_context.update(decision_makers_context)
                    except Exception as e:
                        print(f"[AI Chat] Erro ao buscar decision makers: {e}")
                    
                    # Buscar employees por departamento
                    try:
                        employees_context = await ContextService.fetch_employees_by_department(session, org_id)
                        internal_context['employees_by_dept'] = employees_context
                    except Exception as e:
                        print(f"[AI Chat] Erro ao buscar employees: {e}")
                    
                    # Incluir statistics quando houver detalhes
                    internal_context['statistics'] = basic_context.get('statistics', {})
            except Exception as e:
                print(f"[AI Chat] Erro ao buscar contexto: {e}")
                # Continuar com contexto vazio ao invés de falhar
                internal_context = {}
        
        # 3. Montar o prompt com contexto
        # Se payload.context não for fornecido, usar o intent detectado automaticamente
        system_context_type = payload.context if payload.context and payload.context != "general" else intent
        system_context = _get_system_context(system_context_type)
        
        # Se temos contexto interno, adicionar como dados estruturados e legíveis para a IA
        context_prompt = ""
        if internal_context:
            formatted_context = _format_context_for_prompt(internal_context)
            print(f"[AI Chat] Contexto formatado para Groq:\n{formatted_context}")
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
        
        # Remover estrutura de seções (SEÇÃO: ) para deixar mais natural
        cleaned_response = re.sub(r'\n?[A-Z][A-Z\s]+:\s*\n', ' ', cleaned_response)
        cleaned_response = re.sub(r'^[A-Z][A-Z\s]+:\s*', '', cleaned_response, flags=re.MULTILINE)
        
        # Remover também seções com **Título:**
        cleaned_response = re.sub(r'\*\*[^*]+:\*\*\s*\n', '', cleaned_response)
        cleaned_response = re.sub(r'\*\*[^*]+:\*\*\s*', '', cleaned_response)
        
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
    base_instructions = """BASE DE DADOS INTERNA - RESPONDA COMO PROSA NATURAL E CONVERSACIONAL:

🔴 INSTRUÇÕES CRÍTICAS E OBRIGATÓRIAS:
- NUNCA responda com JSON, tabelas, tópicos, listas numeradas ou títulos.
- NUNCA responda como um formato de dicionário ou estrutura.
- TODO o seu texto deve ser em prosa corrida/parágrafos naturais, como um assistente de vendas e prospecção conversando com o usuário.
- Se a pergunta é apenas sobre a empresa e você não tem muitos dados, VOCÊ PODE dar uma breve descrição do que a empresa faz (da sua base de conhecimento aberta).
- MAS, você DEVE também inserir os dados mapeados fornecidos a você entre "DADOS INTERNOS". Inclua informações como CNPJ e Site na sua resposta de forma natural se eles existirem no texto de entrada.

EXEMPLOS DE RESPOSTA CORRETA EM PROSA (Misto de conhecimento com o banco + dados extraídos):
"A Empresa Tal é uma corporação do setor industrial. Nosso banco de dados informa que o CNPJ é 00.000.000/0001-00 e o site é empresatal.com.br. (Se houver funcionários na lista: Entre os contatos, pude identificar o João Silva que é Analista e a Mariana que atua no RH...)"

REGRAS SOBRE LER DADOS DO BANCO EM "INÍCIO DOS DADOS INTERNOS MAPEADOS DO SISTEMA":
- Todo o conteúdo lá dentro é referente ESTRITAMENTE ao CNPJ e site e contatos da empresa requisitada.
- Nunca ignore esses dados, faça o possível para encaixá-los na sua resposta natural.
- 🔴 É PROIBIDO inventar/alucinar nomes de funcionários e cargos. Se a lista de funcionários/tomadores de decisão de dados internos estiver vazia, diga apenas que "ainda não mapeamos os funcionários dessa empresa na base de dados".
- O exemplo dado acima é APENAS um formato. Nunca copie os nomes "João Silva" ou "Mariana" para a resposta real."""
    
    contexts = {
        "hierarchy_analysis": f"""{base_instructions}

Você é um assistente especializado em análise de negócios. Leia e assimile os DADOS INTERNOS fornecidos logo abaixo. Dê insights misturando os dados do banco com a sua compreensão comercial, lembrando 100% de escrever em formato de redação/parágrafos e sem seções/tópicos.""",
        
        "contacts": f"""{base_instructions}

Você é especialista em contatos B2B.
Liste os contatos e os departamentos EXATOS que encontrar nos dados informados pela API, MAS o faça sempre em prosa, falando em parágrafos normais.""",
        
        "general": f"""{base_instructions}

Você é assistente B2B. Resuma as informações recebidas dos "DADOS INTERNOS" de forma muito cortês e proativa, em texto fluido natural sem estrutura de tópicos.""",
        
        "strategy": f"""{base_instructions}

Você é estrategista B2B analisando dados organizacionais.
Sempre fale em prosa livre de marcações especiais de texto.""",
        
        "relationship": f"""{base_instructions}

Você é especialista em relacionamentos de vendas B2B. Apresente os fatos em texto corrido e discuta conexões entre as pessoas se aplicável."""
    }
    
    return contexts.get(context, contexts["general"])
