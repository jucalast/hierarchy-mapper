"""
Serviço de Estratégia e Consultoria de Vendas B2B.
Analisa a situação atual do negócio, histórico de comunicações (WhatsApp, E-mail) e dados do CRM
usando as melhores metodologias de vendas (MEDDPICC, SPIN Selling, Challenger Sale) para sugerir
ações comerciais de alta performance de forma dinâmica.
"""
import json
import re
from datetime import datetime
from typing import Any, Dict, List
from core.observability.logging_config import get_logger
from core.llm.router import ask_llm
from core.llm.base import LLMTier
from modules.ai.service.context.business_context_service import BusinessContextService

log = get_logger(__name__)

class SalesStrategyService:
    """
    Serviço dedicado à inteligência comercial B2B.
    Aplica técnicas consagradas de vendas para diagnosticar negócios e gerar planos de ação impecáveis.
    """

    async def analyze_and_suggest_actions(self, messages: List[Dict[str, Any]], org_id: int | None = None, contact_name: str = "", phone: str = "") -> Dict[str, Any]:
        """
        Analisa o estado real do negócio (CRM + comunicações) e gera sugestões
        personalizadas cobrindo todas as ferramentas disponíveis.
        """
        log.info("sales_strategy_service.analyze_and_suggest_actions", org_id=org_id)

        # ── 1. Extrai contexto estruturado do histórico de mensagens ──────────
        from modules.agent.service.helpers import _get_tools_called
        executed_tools = _get_tools_called(messages)
        
        history_serialized = []
        crm_snapshot = {
            "org_name": None, "deal_id": None, "deal_stage": None, "deal_value": None,
            "pending_activities": [], "contacts": [], "last_whatsapp": None,
            "last_email": None, "items_quoted": [], "competitors": [],
            "prospect_evaluation": None,
        }
        active_skill_rules = ""

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            # Extrai regras injetadas pelo sub-agente (skill) no histórico
            if isinstance(content, str) and "REGRAS OBRIGATÓRIAS" in content:
                import re
                m = re.search(r"(REGRAS OBRIGATÓRIAS.*?)(?=\n\n|$)", content, re.DOTALL)
                if m:
                    active_skill_rules = m.group(1)
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                    elif item.get("type") == "tool_result":
                        tool_name = item.get("tool_name", "")
                        tool_content = str(item.get("content", ""))
                        if len(tool_content) > 8000:
                            tool_content = tool_content[:8000] + "... [truncado]"
                        text_parts.append(f"[{tool_name}]: {tool_content}")

                        # Extrai snapshots do CRM dos resultados das ferramentas
                        try:
                            # Tenta parsear JSON robustamente
                            tc_data = {}
                            if isinstance(item.get("content"), dict):
                                tc_data = item["content"]
                            else:
                                tc_data = json.loads(item.get("content", "{}") or "{}")
                                
                            if tool_name == "pipedrive_get_org" and tc_data.get("org"):
                                crm_snapshot["org_name"] = tc_data["org"].get("name")
                            elif tool_name == "pipedrive_get_activities":
                                acts = tc_data.get("activities", []) or tc_data.get("pending", []) or []
                                crm_snapshot["pending_activities"] = [
                                    {"id": a.get("id"), "subject": a.get("subject"), "due": a.get("due_date"), "person": a.get("person_name")}
                                    for a in acts if not a.get("done")
                                ]
                            elif tool_name == "pipedrive_get_deals":
                                deals = tc_data.get("deals", []) or []
                                if deals:
                                    d = deals[0]
                                    crm_snapshot["deal_id"] = d.get("id")
                                    crm_snapshot["deal_stage"] = d.get("stage_name") or d.get("stage")
                                    crm_snapshot["deal_value"] = d.get("value")
                            elif tool_name == "pipedrive_get_persons":
                                persons = tc_data.get("persons", []) or []
                                crm_snapshot["contacts"] = [
                                    {"name": p.get("name"), "phone": p.get("phone"), "email": p.get("email"), "id": p.get("id")}
                                    for p in persons
                                ]
                            elif tool_name == "whatsapp_get_messages":
                                msgs_list = tc_data.get("messages", []) or []
                                if msgs_list:
                                    crm_snapshot["last_whatsapp"] = msgs_list[-1] if msgs_list else None
                            elif tool_name == "email_get_contact_history":
                                emails_list = tc_data.get("emails", []) or []
                                if emails_list:
                                    crm_snapshot["last_email"] = emails_list[-1] if emails_list else None
                            elif tool_name == "evaluate_prospects":
                                best_prospects = tc_data.get("best_prospects", [])
                                overall_strategy = tc_data.get("overall_strategy", "")
                                if best_prospects or overall_strategy:
                                    crm_snapshot["prospect_evaluation"] = {
                                        "best_prospects": best_prospects,
                                        "overall_strategy": overall_strategy
                                    }
                        except Exception:
                            # Fallback: extrai dados do texto formatado usando expressões regulares
                            try:
                                import re
                                if "pipedrive" in tool_name or tool_name == "evaluate_prospects":
                                    # Extrai nome da organização
                                    m_org = re.search(r'🏢 ORG:\s*([^\n]+)', tool_content)
                                    if m_org:
                                        crm_snapshot["org_name"] = m_org.group(1).strip()
                                    
                                    # Extrai informações do Deal
                                    m_deal = re.search(r'•\s*\[ID:([^\]]+)\]\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*Funil:\s*([^\n]+)', tool_content)
                                    if m_deal:
                                        crm_snapshot["deal_id"] = int(m_deal.group(1)) if m_deal.group(1).isdigit() else m_deal.group(1)
                                        crm_snapshot["deal_stage"] = m_deal.group(5).strip()
                                        try:
                                            crm_snapshot["deal_value"] = float(m_deal.group(4).replace("R$", "").replace(",", "").strip())
                                        except:
                                            crm_snapshot["deal_value"] = 0.0

                                    # Extrai contatos
                                    contact_matches = re.finditer(r'•\s*\[ID:([^\]]+)\]\s*([^(]+?)(?:\s*\(([^)]+)\))?(?:\s*-\s*Cargo:\s*(.*?))?(?:\s*\[.*\])?$', tool_content, re.MULTILINE)
                                    for m in contact_matches:
                                        c_id = m.group(1).strip()
                                        c_name = m.group(2).strip()
                                        c_info = m.group(3).strip() if m.group(3) else ""
                                        c_id_val = None if c_id == "LocalDB" else int(c_id) if c_id.isdigit() else c_id
                                        email = c_info if "@" in c_info else None
                                        phone = c_info if c_info and "@" not in c_info and c_info != "sem contato" else None
                                        if not any(c["name"] == c_name for c in crm_snapshot["contacts"]):
                                            crm_snapshot["contacts"].append({
                                                "name": c_name,
                                                "phone": phone,
                                                "email": email,
                                                "id": c_id_val
                                            })

                                    # Extrai atividades pendentes
                                    act_matches = re.finditer(r'◯\s*\[ID:([^\]]+)\]\s*([^(]+?)\s*\(venc:\s*([^)]+)\)(?:\s*\|\s*([^\n]+))?', tool_content)
                                    for m in act_matches:
                                        a_id = m.group(1).strip()
                                        a_subject = m.group(2).strip()
                                        a_due = m.group(3).strip()
                                        a_id_val = int(a_id) if a_id.isdigit() else a_id
                                        if not any(a["id"] == a_id_val for a in crm_snapshot["pending_activities"]):
                                            crm_snapshot["pending_activities"].append({
                                                "id": a_id_val,
                                                "subject": a_subject,
                                                "due": a_due,
                                                "person": None
                                            })

                                    # Extrai avaliação de prospectos
                                    if tool_name == "evaluate_prospects":
                                        strategy_match = re.search(r'💡 ESTRATÉGIA GERAL:\s*(.*)', tool_content, re.DOTALL)
                                        overall_strategy = strategy_match.group(1).strip() if strategy_match else ""
                                        
                                        best_prospects = []
                                        prospect_matches = re.finditer(r'•\s*([^-(\n]+?)\s*\(([^)]+)\)\s*\|\s*SCORE:\s*(\d+)\s*\|\s*TIER:\s*([A-C])', tool_content)
                                        for pm in prospect_matches:
                                            p_name = pm.group(1).strip()
                                            p_role = pm.group(2).strip()
                                            p_score = int(pm.group(3))
                                            p_tier = pm.group(4).strip()
                                            best_prospects.append({
                                                "name": p_name,
                                                "role": p_role,
                                                "suitability_score": p_score,
                                                "suitability_tier": p_tier
                                            })
                                        if best_prospects or overall_strategy:
                                            crm_snapshot["prospect_evaluation"] = {
                                                "best_prospects": best_prospects,
                                                "overall_strategy": overall_strategy
                                            }
                            except Exception as parse_err:
                                log.warning(f"Erro ao parsear dados com regex em strategy.py: {parse_err}")

                content = "\n".join(text_parts)

            history_serialized.append({"role": role, "content": str(content)})

        # ── 1.5. Injeção Hard de Dados Reais do CRM (Prevenção de Alucinação) ──
        if org_id:
            try:
                from modules.crm.service.pipedrive_service import pipedrive_service
                details = await pipedrive_service.get_organization_details(org_id)
                if isinstance(details, dict):
                    # Deals
                    deals = details.get("deals") or []
                    if deals:
                        d = deals[0]
                        crm_snapshot["deal_id"] = d.get("id")
                        crm_snapshot["deal_stage"] = d.get("stage_name") or d.get("stage") or d.get("stage_id")
                        crm_snapshot["deal_value"] = d.get("value")
                    # Activities
                    activities = details.get("activities") or []
                    if activities:
                        crm_snapshot["pending_activities"] = [
                            {"id": a.get("id"), "subject": a.get("subject"), "due": a.get("due_date"), "person": a.get("person_name")}
                            for a in activities if not a.get("done")
                        ]
                    # Contacts
                    persons = details.get("persons") or []
                    if persons:
                        crm_snapshot["contacts"] = []
                        for p in persons:
                            phone_list = p.get("phone", [])
                            email_list = p.get("email", [])
                            phone_val = next((x.get("value") for x in phone_list if x.get("value")), None) if isinstance(phone_list, list) else None
                            email_val = next((x.get("value") for x in email_list if x.get("value")), None) if isinstance(email_list, list) else None
                            crm_snapshot["contacts"].append({
                                "name": p.get("name"), 
                                "phone": phone_val, 
                                "email": email_val, 
                                "id": p.get("id")
                            })
            except Exception as e:
                log.warning(f"Erro ao buscar snapshot hard do CRM para estrategia: {e}")

        # ── 2. Carrega contexto de negócio ────────────────────────────────────
        business_context = await BusinessContextService.get_tenant_context()
        biz_data_str = json.dumps(business_context, indent=2, ensure_ascii=False) if business_context else "{}"

        # ── 3. Monta snapshot de estado para o LLM ───────────────────────────
        has_pending = bool(crm_snapshot["pending_activities"])
        pending_str = json.dumps(crm_snapshot["pending_activities"], ensure_ascii=False) if has_pending else "nenhuma"
        contacts_str = json.dumps(crm_snapshot["contacts"], ensure_ascii=False) if crm_snapshot["contacts"] else "nenhum"

        # Extrai entryId do último email para forçar reply na thread
        last_email_entry_id = None
        last_email_subject = None
        if crm_snapshot.get("last_email"):
            last_email_entry_id = crm_snapshot["last_email"].get("entryId") or crm_snapshot["last_email"].get("entry_id")
            last_email_subject = crm_snapshot["last_email"].get("subject", "")

        today = datetime.now().strftime("%A, %d/%m/%Y")
        
        # Lista de ferramentas que acabaram de ser executadas para injetar no prompt
        executed_tools_str = ", ".join(executed_tools) if executed_tools else "nenhuma ferramenta de escrita executada neste turno"

        email_thread_rule = (
            f"REGRA CRÍTICA DE EMAIL: Há uma thread ativa com este contato (último email: \"{last_email_subject}\", "
            f"entryId='{last_email_entry_id}'). Como é proibido sugerir email direto, se for sugerir acompanhamento por email, sugira CRIAR UMA TAREFA NO CRM pedindo para responder a thread."
            if last_email_entry_id else
            "Não há thread de email anterior. Se sugerir email (em caso de tarefa pendente ou pedido direto), sugira OBRIGATORIAMENTE criar uma tarefa no CRM (pipedrive_create_task)."
        )

        prospects_section = ""
        if crm_snapshot.get("prospect_evaluation"):
            pe = crm_snapshot["prospect_evaluation"]
            prospects_section = (
                f"\n## AVALIAÇÃO DE PROSPECTOS (evaluate_prospects):\n"
                f"- Estratégia Geral: {pe.get('overall_strategy', '')}\n"
                f"- Melhores Prospectos (Tier A): {json.dumps(pe.get('best_prospects', []), ensure_ascii=False)}\n"
                f"INSTRUÇÃO: Priorize ações para os prospectos Tier A identificados nesta avaliação.\n"
            )

        system_prompt = f"""Você é o Diretor Comercial B2B e Coach de Vendas Sênior do Tenant.
Sua missão: analisar TODO o contexto disponível e gerar um conjunto COMPLETO e PERSONALIZADO de próximos passos.

## CONTEXTO DA EMPRESA:
- Empresa: {crm_snapshot['org_name'] or 'Não identificada'}
- ID do Negócio: {crm_snapshot['deal_id'] or 'Não encontrado'}
- Etapa Atual: {crm_snapshot['deal_stage'] or 'N/A'}

## REGRAS DE GERAÇÃO DE TEXTO (CRÍTICO):
É ESTRITAMENTE PROIBIDO adicionar o seu nome, cargo (ex: Diretor Comercial, etc) ou assinatura ao final das mensagens geradas (WhatsApp, Email ou Scripts). Termine sempre APENAS com 'Atenciosamente,', pois a assinatura oficial do usuário será injetada automaticamente pelo sistema.

## FERRAMENTAS JÁ EXECUTADAS NESTA SESSÃO (PROIBIDO REPETIR):
{executed_tools_str}

## REGRA DE OURO DA REDUNDÂNCIA (ZERO TOLERANCE):
1. Se uma ferramenta de escrita (whatsapp_send_message, email_send, pipedrive_create_person, pipedrive_update_task) já consta na lista acima, é PROIBIDO sugeri-la novamente para o mesmo alvo.
2. Se o histórico mostra que o contato já foi vinculado ao deal ou cadastrado, NÃO sugira `pipedrive_create_person` ou vinculação.
3. Se a tarefa foi marcada como concluída no histórico recente, NÃO sugira 'Marcar como concluída'.
4. **CADASTRO DE PESSOAS (CRÍTICO)**: Analise a lista 'Contatos já no Pipedrive' abaixo. 
   - Se uma pessoa possui um campo 'id' numérico (não nulo), ela JÁ ESTÁ cadastrada no Pipedrive. É terminantemente PROIBIDO sugerir `pipedrive_create_person` para ela.
   - Se uma pessoa possui 'id': null, ela está apenas no Banco Local/WhatsApp e DEVE ser sugerida para cadastro no Pipedrive (`pipedrive_create_person`) se for um decisor relevante.
   - Verifique variações de nomes. Se "Edson Luís de Almeida" já tem ID, não sugira cadastrar "Edson Luís".

## CONTEXTO DO NEGÓCIO (TENANT):
{biz_data_str}

## FERRAMENTAS DISPONÍVEIS PARA O AGENTE (use nos prompts das ações):
- whatsapp_send_message: envia WhatsApp (contact, phone, message, org_name)
- email_send: envia email NOVO sem thread existente (to, subject, body, attachment_name) - SÓ USE SE A TAREFA FOR ENVIAR EMAIL.
- email_reply: responde na thread existente (entry_id, body) - SÓ USE SE A TAREFA FOR RESPONDER EMAIL.
- pipedrive_create_task: cria tarefa no CRM (subject, task_type=[call|meeting|task|deadline], due_date, deal_id, org_name, note)
- pipedrive_update_task: atualiza ou conclui tarefa existente (activity_id, done=true/false, subject, due_date)
- pipedrive_update_deal: atualiza deal (deal_id, fields)
- pipedrive_create_note: cria nota no Pipedrive (content, deal_id, person_id, org_id)
- whatsapp_get_messages: busca histórico WhatsApp (contact, phone, org_name)
- email_get_contact_history: busca histórico email (contact_name, org_name)

## {email_thread_rule}

## ESTADO ATUAL DO CRM:
- Empresa: {crm_snapshot.get('org_name') or 'ver histórico'}
- Deal ID: {crm_snapshot.get('deal_id') or 'ver histórico'} | Etapa: {crm_snapshot.get('deal_stage') or 'desconhecida'} | Valor: {crm_snapshot.get('deal_value') or 'não informado'}
- Atividades pendentes: {pending_str}
- Contatos já no Pipedrive (id != null significa já cadastrado): {contacts_str}
- Contato principal: {contact_name or 'ver histórico'} {('| Tel: ' + phone) if phone else ''}
- Hoje: {today}
{prospects_section}
## CICLO B2B END-TO-END BASEADO NO CONTEXTO:
1. TAREFA EM EXECUÇÃO (FOCO ABSOLUTO): Se você foi chamado para realizar uma atividade específica (ex: ID 8153 - Otimização), sua PRIMEIRA missão é executar o trabalho comercial. 
   - Se o objetivo é enviar algo (proposta, apresentação, otimização), você DEVE obrigatoriamente gerar o rascunho e propor o envio (`whatsapp_send_message` ou `email_send`). 
   - NÃO finalize apenas com sugestões genéricas; o card de envio deve ser a ação principal.
2. PRÓXIMOS PASSOS (ESTRATÉGIA): Após realizar a ação principal, analise a lista de 'Atividades pendentes' do Pipedrive fornecida no contexto.
   - Suas sugestões de 'Próximos Passos' DEVEM ser baseadas nas tarefas REAIS que já existem no CRM para esta empresa. 
   - Se existe uma tarefa de 'Ligar em 3 dias', sugira 'Criar tarefa: Follow-up da otimização' apenas se for realmente um novo passo necessário. 
   - Priorize concluir a tarefa atual (`pipedrive_update_task`) apenas APÓS o envio da mensagem.
2. COMUNICAÇÃO POR E-MAIL (REGRA CRÍTICA - EXCEÇÃO DA TAREFA ATUAL): Quando você está apenas sugerindo os próximos passos (proativamente), é TERMINANTEMENTE PROIBIDO sugerir enviar um e-mail diretamente. Você DEVE sugerir a CRIAÇÃO DE UMA TAREFA NO CRM (`pipedrive_create_task`). 
   - EXCEÇÃO ABSOLUTA: Se a tarefa atual em execução (o motivo pelo qual o usuário te chamou agora) for LITERALMENTE "Enviar e-mail de apresentação", "Enviar proposta", etc., AÍ SIM você DEVE sugerir a ação `email_send` ou `email_reply` com o rascunho do e-mail pronto em um card de aprovação (usando o plano de prospecção e contexto para gerar o rascunho). Resumindo: Sugerir proativamente = Criar Tarefa. Executar a tarefa de e-mail = Gerar e Enviar E-mail.
3. CADASTRO: Para novos decisores identificados que possuem 'id': null na lista acima, a PRIMEIRA ação deve ser "Cadastrar [Nome] no Pipedrive" (pipedrive_create_person). Se eles já possuem ID numérico, pule para "Criar tarefa: Enviar e-mail...".
4. FOLLOW-UP DE VALOR (SEM RESPOSTA): Se o cliente ignorou o contato inicial, NÃO envie mensagens genéricas de cobrança. Sugira enviar um Insight de Mercado baseado nos diferenciais da empresa e termine sugerindo uma reunião rápida.
5. DIAGNÓSTICO (REUNIÃO): O objetivo de todo follow-up frio é marcar uma call de diagnóstico para mapear necessidades e dores.
6. NEGOCIAÇÃO: Se a reunião já ocorreu ou amostras foram enviadas, o foco passa a ser defender o custo-benefício da solução frente à concorrência e fechar a proposta.

## A JORNADA ATÉ A REUNIÃO (O CAMINHO LÓGICO):
Todo o seu raciocínio deve ser voltado para agendar uma reunião. Os passos sequenciais obrigatórios no Pipedrive para chegar lá são:
1. Contato decisor cadastrado no CRM (pipedrive_create_person).
2. Contato decisor vinculado ao Negócio/Deal (pipedrive_update_deal com o ID do contato).
3. Tarefa criada para enviar a primeira comunicação (pipedrive_create_task).
4. Envio da primeira comunicação (email_send / whatsapp_send_message).
5. Tarefa de Follow-up criada após o envio inicial (pipedrive_create_task).
6. Execução de Follow-up (até agendar).
7. Criação da tarefa/evento de Reunião no calendário do CRM.

## GAP ANALYSIS (O que falta?):
1. TAREFA CUMPRIDA: Se a tarefa original já atingiu seu objetivo, sugira concluí-la (pipedrive_update_task com done=true).
2. PERSONA SEM REGISTRO: Compare os nomes com a lista de 'Contatos já no Pipedrive'. Se alguém não tem ID, sugira `pipedrive_create_person`.
3. NEGÓCIO ÓRFÃO: Verifique a seção 'Estado Atual do CRM'. Se o Negócio (Deal) não possui contato vinculado (ou person_id é nulo), e você identificou o decisor, a PRIMEIRA sugestão estratégica deve ser 'Vincular decisor ao Negócio' (pipedrive_update_deal vinculando o ID do decisor ao Deal).
4. LACUNA NA JORNADA: Se o contato está vinculado, mas não existe tarefa de comunicação pendente, sugira criar a tarefa de 'Enviar Apresentação' ou 'Realizar Ligação'.
5. REGRA DE OURO DA REDUNDÂNCIA: Se o 'id' do contato não for null, ele JÁ ESTÁ CADASTRADO. NÃO sugira duplicatas.
6. EXAUSTIVIDADE: Gere de 5 a 20 sugestões abrangendo as lacunas e também contatos secundários.
7. SEQUÊNCIA LÓGICA MÁXIMA: Nunca sugira enviar um e-mail direto se o contato principal sequer está vinculado ao Deal. A organização do CRM vem primeiro.

## REGRAS PARA AS SUGESTÕES:
1. Gere de 5 a 20 ações — cubra TODAS as categorias relevantes.
2. Baseie CADA sugestão no contexto real do histórico.
3. Para criar tarefas no Pipedrive, o prompt DEVE usar a ferramenta e incluir um aviso estrito: "Use pipedrive_create_task com subject='...', etc. AVISO: Seu único objetivo é CRIAR a tarefa. É PROIBIDO executar a tarefa ou gerar o e-mail agora."
4. PREVENIR DUPLICIDADE: Se o contato já existe, PROIBIDO sugerir `pipedrive_create_person`.
8. RECONHECER O ESTÁGIO DO DEAL (PREVENIR REGRESSÃO): Se já houve cotação ou visita, não sugira ações de "prospecção fria". Foque em fechamento e negociação.
9. PREVENIR DUPLICIDADE: Se o contato já existe no CRM (verifique a lista 'Contatos já no Pipedrive'), PROIBIDO sugerir `pipedrive_create_person`.
10. Se a tarefa principal já foi realizada (ex: Encontrar contato concluído), a primeira sugestão DEVE ser marcar a atividade original como concluída (usando pipedrive_update_task).

## REGRAS PARA O CAMPO "label":
- NÃO inclua o nome do canal no label (ex: PROIBIDO "WhatsApp: Cobrar retorno", CORRETO: "Cobrar retorno da cotação de Outubro")
- O canal já é exibido separadamente na interface — o label deve descrever a AÇÃO, não o canal
- Para `tarefa_crm`: seja específico sobre O QUE a tarefa registra. PROIBIDO "Atualizar Deal [empresa]". CORRETO: "Avançar deal para etapa Proposta", "Registrar visita realizada em [data]", "Criar tarefa: ligar para [contato] até [data]"
- Para `reuniao`: indique o propósito — "Agendar reunião de apresentação", "Reagendar visita técnica cancelada"
- Máximo 55 caracteres. Sem nome de empresa no label (já aparece no contexto)

{f"## {active_skill_rules}" if active_skill_rules else ""}

## FORMATO DE RESPOSTA (JSON estrito, sem markdown externo):
{{
  "diagnostico": {{
    "temperatura": "Quente|Morno|Frio|Bloqueado",
    "fase_funil": "Qualificacao|Proposta|Negociacao|Fechamento",
    "resumo_situacao": "2-3 frases descrevendo o estado real do negócio com base no histórico",
    "gap_critico": "o maior obstáculo para avançar agora",
    "proxima_janela": "quando/como agir para maximizar chances de fechamento"
  }},
  "acoes": [
    {{
      "label": "Texto curto e específico da AÇÃO (máx 55 chars, sem nome de canal, sem nome de empresa)",
      "categoria": "whatsapp|email|tarefa_crm|reuniao|estrategia",
      "razao": "por que fazer ISSO agora (1 frase com dado real do histórico)",
      "prompt": "Instrução completa e autossuficiente para o agente executar. Ex: 'Use whatsapp_send_message com contact=\\"Mariana Ruiz\\", phone=\\"5511950374342\\", org_name=\\"Master Sense\\", message=\\"[mensagem completa e pronta]\\"'"
    }}
  ]
}}"""

        prompt_user = f"""Analise o histórico completo desta conversa e gere as sugestões.

CONTATO PRINCIPAL: {contact_name or 'identificar no histórico'} {('| Tel: ' + phone) if phone else ''}
ATIVIDADES PENDENTES NO CRM: {pending_str}

Leia TODO o histórico acima (WhatsApp, emails, dados Pipedrive) e gere ações personalizadas.
PROIBIDO ações genéricas — cite fatos reais (preços, itens, datas, objeções) encontrados no histórico.
Se nenhuma atividade pendente existe, é OBRIGATÓRIO sugerir a criação de pelo menos uma tarefa de acompanhamento no Pipedrive."""

        try:
            res = await ask_llm(
                prompt=prompt_user,
                system=system_prompt,
                history=history_serialized,
                json_mode=True,
                temperature=0.15,
                tier=LLMTier.STANDARD,
            )

            raw = (res.json_data if res.json_data else {}) or {}
            if not raw and res.text:
                txt = res.text.strip()
                if txt.startswith("```"):
                    txt = re.sub(r"^```\w*\n?", "", txt).rstrip("`").strip()
                try:
                    raw = json.loads(txt, strict=False)
                except Exception:
                    pass

            diagnostico = raw.get("diagnostico", {})
            acoes = raw.get("acoes", [])

            # Badge de temperatura
            temp = diagnostico.get("temperatura", "")
            temp_badge = {"Quente": "🔴 Quente", "Morno": "🟡 Morno", "Frio": "🔵 Frio", "Bloqueado": "🚫 Bloqueado"}.get(temp, "⚪ Desconhecido")

            summary_md = (
                f"### 🎯 Diagnóstico Comercial — {diagnostico.get('fase_funil', '')}\n\n"
                f"| | |\n|:---|:---|\n"
                f"| **Temperatura** | {temp_badge} |\n"
                f"| **Situação** | {diagnostico.get('resumo_situacao', '')} |\n"
                f"| **Gap crítico** | {diagnostico.get('gap_critico', '')} |\n"
                f"| **Janela de ação** | {diagnostico.get('proxima_janela', '')} |\n\n"
                "---\n"
                "### ⚡ Próximos Passos Personalizados\n"
                "*(Clique para o agente executar automaticamente)*\n\n"
            )

            categoria_icon = {
                "whatsapp": "💬", "email": "📧", "tarefa_crm": "📋",
                "reuniao": "📅", "estrategia": "🎯",
            }

            normalized_actions = []
            for act in acoes:
                label = str(act.get("label", "")).strip()
                razao = str(act.get("razao", "")).strip()
                prompt_str = str(act.get("prompt", "")).strip()
                cat = act.get("categoria", "")
                icon = categoria_icon.get(cat, "•")

                if not label:
                    continue
                if not prompt_str:
                    prompt_str = label

                summary_md += f"**{icon} {label}**\n_{razao}_\n\n"
                normalized_actions.append({"label": label, "prompt": prompt_str, "razao": razao, "categoria": cat})

            return {"ok": True, "actions": normalized_actions, "summary": summary_md}

        except Exception as e:
            log.exception("sales_strategy_service.analyze_and_suggest_actions.failed", error=str(e))
            return {
                "ok": False,
                "actions": [],
                "summary": f"Erro ao executar o diagnóstico avançado: {str(e)}"
            }

# Instância global single-source of truth
sales_strategy_service = SalesStrategyService()
