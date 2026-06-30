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

# Critérios de conclusão de estágio indexados por nome normalizado (lowercase, sem espaço extra).
# IDs NÃO estão aqui — o pipeline real é consultado via Pipedrive API em runtime.
# Novos estágios criados no Pipedrive que não batem nenhuma chave simplesmente não geram sugestão de avanço.
_STAGE_RULES: Dict[str, Dict[str, str]] = {
    "entrada (novos negócios)": {
        "goal": "Identificar e cadastrar o decisor de compras no CRM com contato (telefone/email)",
        "completion_signs": "decisor encontrado e cadastrado no Pipedrive com telefone ou email válido",
        "next_task_type": "call",
        "next_task_hint": "Ligar para qualificar necessidade, budget e urgência",
    },
    "qualificação": {
        "goal": "Confirmar interesse, budget e mapear a dor/necessidade real",
        "completion_signs": "ligação ou contato de qualificação realizado, interesse confirmado ou dor mapeada no histórico",
        "next_task_type": "meeting",
        "next_task_hint": "Agendar reunião de apresentação ou demonstração do produto/solução",
    },
    "contatado": {
        "goal": "Reunião de apresentação agendada e confirmada",
        "completion_signs": "reunião marcada com data e horário definidos, criada no Pipedrive ou confirmada no histórico",
        "next_task_type": "meeting",
        "next_task_hint": "Confirmar presença e preparar pauta/material para a reunião",
    },
    "reunião agendada": {
        "goal": "Reunião realizada com levantamento completo de necessidades",
        "completion_signs": "reunião aconteceu, feedback ou ata registrada, próximo passo combinado com o cliente",
        "next_task_type": "task",
        "next_task_hint": "Preparar proposta comercial personalizada com base nas necessidades levantadas",
    },
    "reunião realizada": {
        "goal": "Proposta comercial enviada ao cliente",
        "completion_signs": "proposta enviada, cotação entregue, valor apresentado ao cliente",
        "next_task_type": "task",
        "next_task_hint": "Follow-up da proposta: marcar retorno para saber a posição do cliente",
    },
    "proposta em andamento": {
        "goal": "Proposta aceita ou em negociação ativa de condições",
        "completion_signs": "cliente respondeu sobre a proposta, negociação de preço/prazo em andamento, contraoferta ou aprovação parcial",
        "next_task_type": "task",
        "next_task_hint": "Negociar condições finais e encaminhar para fechamento do pedido",
    },
    "entrada (carteira)": {
        "goal": "Retomar contato com cliente da carteira e identificar nova necessidade",
        "completion_signs": "contato reativado, interesse em novo pedido ou recompra identificado no histórico",
        "next_task_type": "call",
        "next_task_hint": "Ligar para mapear necessidade e coletar informações para nova proposta",
    },
    "contato": {
        "goal": "Necessidade mapeada, pronto para elaborar proposta de recompra",
        "completion_signs": "necessidade e itens de interesse confirmados pelo cliente",
        "next_task_type": "task",
        "next_task_hint": "Elaborar e enviar proposta de recompra com condições atualizadas",
    },
    "proposta": {
        "goal": "Proposta aprovada e pedido colocado",
        "completion_signs": "proposta aceita, pedido confirmado pelo cliente ou programação de entrega solicitada",
        "next_task_type": "task",
        "next_task_hint": "Confirmar programação de entrega e acompanhar emissão do pedido",
    },
}


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
                        
                        p_id = d.get("person_id")
                        if isinstance(p_id, dict):
                            crm_snapshot["deal_person_id"] = p_id.get("value")
                            crm_snapshot["deal_person_name"] = p_id.get("name")
                        else:
                            crm_snapshot["deal_person_id"] = p_id
                            crm_snapshot["deal_person_name"] = None
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

        # ── 1.8. Resolve contexto de progressão de estágio via Pipedrive ────────
        _raw_stage = crm_snapshot.get("deal_stage") or ""
        _stage_rule = _STAGE_RULES.get(_raw_stage.lower().strip())
        _next_stage_name: str | None = None
        _deal_id_for_prompt = crm_snapshot.get("deal_id") or "VER_HISTÓRICO"

        if _stage_rule:
            try:
                from modules.crm.service.pipedrive_service import pipedrive_service
                _all_stages = await pipedrive_service.get_all_stages_full()
                # Acha o stage atual pelo nome
                _current_entry = next(
                    ((sid, sdata) for sid, sdata in _all_stages.items()
                     if sdata.get("name", "").lower().strip() == _raw_stage.lower().strip()),
                    None,
                )
                if _current_entry:
                    _cur_id, _cur_data = _current_entry
                    _cur_order = _cur_data.get("order_nr", 0)
                    _cur_pipeline = _cur_data.get("pipeline_id")
                    # Próximo stage = mesmo pipeline, menor order_nr acima do atual
                    _best_order = None
                    for _sid, _sdata in _all_stages.items():
                        if _sdata.get("pipeline_id") != _cur_pipeline:
                            continue
                        _o = _sdata.get("order_nr", 0)
                        if _o > _cur_order and (_best_order is None or _o < _best_order):
                            _best_order = _o
                            _next_stage_name = _sdata.get("name")
            except Exception as _e:
                log.warning("sales_strategy.stage_progression_lookup_failed", error=str(_e))

        if _stage_rule and _next_stage_name:
            stage_progression_section = f"""
## PASSO 6 — INTELIGÊNCIA DE PROGRESSÃO DE FUNIL (execute APÓS os Passos 1-5):
Analise se o objetivo do estágio atual JÁ foi cumprido e se é hora de avançar o deal.

| Campo | Valor |
|---|---|
| Estágio atual | **{_raw_stage}** |
| Objetivo deste estágio | {_stage_rule['goal']} |
| Sinais de conclusão | {_stage_rule['completion_signs']} |
| Próximo estágio | **{_next_stage_name}** |
| Tarefa recomendada no novo estágio | {_stage_rule['next_task_hint']} (tipo: {_stage_rule['next_task_type']}) |

REGRAS DO PASSO 6:
- Se o histórico mostrar que os "Sinais de conclusão" acima foram atingidos → INCLUA obrigatoriamente uma sugestão de avanço.
- A sugestão de avanço deve ser a PRIMEIRA (ou segunda, após desbloqueio crítico) da lista de ações.
- O prompt da sugestão deve instruir o agente a executar EM SEQUÊNCIA:
  1. `pipedrive_advance_deal` com target_stage='next' e deal_id={_deal_id_for_prompt}
  2. `pipedrive_create_task` com task_type='{_stage_rule['next_task_type']}', a nota de contexto e o objetivo do novo estágio
- label sugerido: "Avançar para {_next_stage_name}" (máx 55 chars)
- categoria: "tarefa_crm"
- razão: cite QUAL sinal de conclusão específico foi detectado no histórico

- Se os sinais de conclusão NÃO foram detectados → NÃO sugira avançar. Foque nas ações do estágio atual.
- Se o negócio pulou etapas (ex: cliente já marcou reunião estando em Qualificação) → sugira avançar diretamente para o estágio correto usando `pipedrive_advance_deal` com `target_stage=<ID_DO_ESTAGIO_CORRETO>`.
"""
        else:
            stage_progression_section = ""

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

## REGRA DE OURO DA REDUNDÂNCIA E DEALS GANHOS (ZERO TOLERANCE):
1. Se uma ferramenta de escrita (whatsapp_send_message, email_send, pipedrive_create_person, pipedrive_update_task) já consta na lista acima, é PROIBIDO sugeri-la novamente para o mesmo alvo.
2. Se o histórico mostra que o contato já foi cadastrado, NÃO sugira `pipedrive_create_person`.
3. Se a tarefa foi marcada como concluída no histórico recente, NÃO sugira 'Marcar como concluída'.
4. **CADASTRO DE PESSOAS E VARIANTES (CRÍTICO)**: Analise a lista 'Contatos já no Pipedrive' abaixo.
   - Se uma pessoa possui um campo 'id' numérico (não nulo), ela JÁ ESTÁ cadastrada no Pipedrive. É terminantemente PROIBIDO sugerir `pipedrive_create_person` para ela.
   - Verifique variações de nomes. Se "Giovanna De Domenico" está na lista local com id: null, mas "Giovanna (Compras)" já tem um ID numérico no Pipedrive, considere que elas são a MESMA pessoa. Portanto, é PROIBIDO sugerir cadastrar "Giovanna De Domenico" (ela já está cadastrada sob a outra variação de nome).
   - O mesmo se aplica a quaisquer variações e sobrenomes similares. Se há correspondência parcial (ex: mesmo primeiro nome e sobrenome, ou iniciais iguais) de alguém que já tem ID, NÃO sugira cadastrar a outra versão.
5. **NEGÓCIOS CONCLUÍDOS/FECHADOS (MUITO CRÍTICO)**: Analise o histórico recente de WhatsApp/comunicações para identificar se o pedido/venda já foi fechado ou colocado (ex: aprovação de layouts, mensagens como 'coloquei o pedido para o dia [data]', 'amostras entregues e layouts aprovados', etc.).
   - Se a venda foi fechada/acordada, mas o Deal no CRM ainda está com status 'open' (ou diferente de won):
     * A PRIMEIRA e principal sugestão deve ser **Marcar negócio como ganho** (usando `pipedrive_update_deal` com `deal_id` e `fields={{ "status": "won" }}`).
     * É TERMINANTEMENTE PROIBIDO sugerir cadastrar outros contatos secundários da empresa no Pipedrive (ex: outros engenheiros, sócios, analistas que não participaram diretamente) ou sugerir tarefas de prospecção fria/outbound. O foco mudou para a operação/entrega.
     * Sugira apenas tarefas de pós-venda/satisfação (ex: follow-up de satisfação ou entrega), e NUNCA cadastros redundantes.

## CONTEXTO DO NEGÓCIO (TENANT):
{biz_data_str}

## FERRAMENTAS DISPONÍVEIS PARA O AGENTE (use nos prompts das ações):
- pipedrive_create_task: cria tarefa no CRM (subject, task_type=[call|meeting|task|deadline], due_date, deal_id, org_name, note)
- pipedrive_update_task: atualiza ou conclui tarefa existente (activity_id, done=true/false, subject, due_date)
- pipedrive_update_deal: atualiza deal (deal_id, fields)
- pipedrive_create_note: cria nota no Pipedrive (content, deal_id, person_id, org_id)
- pipedrive_advance_deal: avança o deal para o próximo estágio do funil (deal_id, target_stage='next' OU ID numérico do estágio de destino)

⛔ PROIBIDO nas sugestões: whatsapp_send_message, email_send, email_reply — essas ações NUNCA devem aparecer como sugestão de próximo passo. Em vez disso, crie uma tarefa no Pipedrive descrevendo o que precisa ser feito (ex: "Criar tarefa: Enviar e-mail de follow-up com contexto da última conversa").

## {email_thread_rule}

## ESTADO ATUAL DO CRM:
- Empresa: {crm_snapshot.get('org_name') or 'ver histórico'}
- Deal ID: {crm_snapshot.get('deal_id') or 'ver histórico'} | Etapa: {crm_snapshot.get('deal_stage') or 'desconhecida'} | Valor: {crm_snapshot.get('deal_value') or 'não informado'}
- Deal vinculado a qual pessoa? ID: {crm_snapshot.get('deal_person_id') or 'NENHUMA PESSOA VINCULADA AO NEGÓCIO!'} (Nome: {crm_snapshot.get('deal_person_name') or 'N/A'})
- Atividades pendentes: {pending_str}
- Contatos já no Pipedrive (id != null significa já cadastrado): {contacts_str}
- Contato principal (alvo): {contact_name or 'ver histórico'} {('| Tel: ' + phone) if phone else ''}
- Hoje: {today}
{prospects_section}

## ALGORITMO OBRIGATÓRIO DE VERIFICAÇÃO E PROGRESSÃO (STEP-BY-STEP):
Você atua como uma máquina de estado. Deve executar mentalmente o seguinte checklist NESTA ORDEM EXATA. Ao encontrar a PRIMEIRA condição falsa, SUA PRINCIPAL SUGESTÃO deve ser a ação corretiva daquele passo.

PASSO 1 (Cadastro): O contato alvo (decisor) existe e tem um 'id' numérico válido na lista "Contatos já no Pipedrive"?
- NÃO: Sua 1ª sugestão DEVE ser "Cadastrar [Contato] no Pipedrive" (`pipedrive_create_person`). Você não pode avançar sem cadastrá-lo.
- SIM: Passe para o Passo 2.

PASSO 2 (Vinculação ao Negócio): O "Deal vinculado a qual pessoa?" mostra o ID do nosso contato alvo ou ele está como "NENHUMA PESSOA"?
- NÃO: Sua 1ª sugestão DEVE ser "Vincular [Contato] ao Negócio" (`pipedrive_update_deal` com `person_id`={{ID do contato}}). 
- SIM (Já está vinculado): Passe para o Passo 3.

PASSO 3 (Geração de Tarefa CRM): Já existe alguma tarefa de comunicação (ex: Enviar E-mail, Ligar) em aberto na lista de "Atividades pendentes"?
- NÃO: Sugira criar a tarefa apropriada (`pipedrive_create_task`). 
- SIM: Passe para o Passo 4.

PASSO 4 (Ação Comercial — SEMPRE via tarefa do Pipedrive):
JAMAIS sugira executar email_send, whatsapp_send_message ou ligação diretamente como próximo passo.
Em vez disso, crie uma tarefa no Pipedrive (`pipedrive_create_task`) descrevendo a ação com contexto completo:
- SE FOR PRIMEIRO CONTATO (Frio): Sugira "Criar tarefa: Enviar e-mail de apresentação para [contato] — abordar [gancho específico do histórico]" (task_type=task).
- SE FOR FOLLOW-UP (Morno/Aguardando): Sugira "Criar tarefa: Cobrar retorno por e-mail/WhatsApp com [contato]" com note resumindo o contexto da última interação.
- SE FOR NEGOCIAÇÃO/PROPOSTA (Quente): Sugira "Criar tarefa: Agendar reunião de diagnóstico" (task_type=meeting) ou "Criar tarefa: Enviar proposta revisada".
- SE FOR LIGAÇÃO: Sugira "Criar tarefa: Ligar para [contato] — [motivo específico]" (task_type=call).
SEMPRE inclua no campo `note` da tarefa o contexto da conversa: o que foi discutido, o que está pendente e o que precisa ser feito.

PASSO 5 (Encerramento da Tarefa): A ação de comunicação (Passo 4) já foi feita no histórico recente?
- SIM: Sugira OBRIGATORIAMENTE "Marcar atividade como concluída" (`pipedrive_update_task` com `done=true`).
- EM SEGUIDA: Nenhuma interação termina sem agenda. Logo após concluir, sugira "Criar tarefa de próximo Follow-up" para daqui a X dias.

{stage_progression_section}

## REGRAS PARA AS SUGESTÕES (SAÍDA JSON):
1. Gere de 5 a 15 ações — começando SEMPRE pelo passo no qual o algoritmo parou e incluindo opções alternativas.
2. Ações de criação de pessoa (`pipedrive_create_person`) só devem aparecer se a pessoa NÃO TEM ID no Pipedrive (ou seja, se é um contato do Banco Local [ID:LocalDB]).
3. **CONTATOS LOCAIS SEM ID (CRÍTICO)**: Se o contato decisor/alvo for um contato do Banco Local e ainda não possuir um ID numérico no Pipedrive:
   - Você DEVE sugerir simultaneamente criá-lo (`pipedrive_create_person`), vinculá-lo ao negócio (`pipedrive_update_deal`) e criar as tarefas de abordagem (`pipedrive_create_task`).
   - Ao sugerir `pipedrive_update_deal` ou `pipedrive_create_task` para esse contato sem ID, você DEVE passar o nome completo dele (string) no campo `person_id` (ex: `person_id="Tatiana Papini"`). O sistema resolverá automaticamente o nome para o ID correto. Nunca use placeholders como 'ID_DA_PESSOA_CRIADA_ACIMA'.
4. Ações de vinculação de negócio (`pipedrive_update_deal`) só se o deal não tiver o person_id correto.

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
      "categoria": "tarefa_crm|reuniao|estrategia",
      "razao": "por que fazer ISSO agora (1 frase com dado real do histórico)",
      "prompt": "Instrução completa e autossuficiente para o agente executar. SEMPRE use pipedrive_create_task ou pipedrive_update_task. NUNCA email_send, email_reply ou whatsapp_send_message. Ex: 'Use pipedrive_create_task com subject=\\"Enviar e-mail de follow-up para [contato]\\", task_type=\\"task\\", due_date=\\"YYYY-MM-DD\\", deal_id=XXX, org_name=\\"[empresa]\\", note=\\"[contexto da última conversa e o que foi discutido]\\"'"
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
                "tarefa_crm": "📋",
                "reuniao": "📅",
                "estrategia": "🎯",
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
