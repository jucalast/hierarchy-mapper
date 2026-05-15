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
from core.logging_config import get_logger
from services.ai.llm.router import ask_llm
from services.ai.llm.base import LLMTier
from services.ai.business_context_service import BusinessContextService

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
        history_serialized = []
        crm_snapshot = {
            "org_name": None, "deal_id": None, "deal_stage": None, "deal_value": None,
            "pending_activities": [], "contacts": [], "last_whatsapp": None,
            "last_email": None, "items_quoted": [], "competitors": [],
        }

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
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
                            tc_data = json.loads(item.get("content", "{}") or "{}")
                            if tool_name == "pipedrive_get_org" and tc_data.get("org"):
                                crm_snapshot["org_name"] = tc_data["org"].get("name")
                            elif tool_name == "pipedrive_get_activities":
                                acts = tc_data.get("activities", []) or []
                                crm_snapshot["pending_activities"] = [
                                    {"id": a.get("id"), "subject": a.get("subject"), "due": a.get("due_date")}
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
                                    {"name": p.get("name"), "phone": p.get("phone"), "email": p.get("email")}
                                    for p in persons if p.get("phone") or p.get("email")
                                ]
                            elif tool_name == "whatsapp_get_messages":
                                msgs_list = tc_data.get("messages", []) or []
                                if msgs_list:
                                    crm_snapshot["last_whatsapp"] = msgs_list[-1] if msgs_list else None
                            elif tool_name == "email_get_contact_history":
                                emails_list = tc_data.get("emails", []) or []
                                if emails_list:
                                    crm_snapshot["last_email"] = emails_list[-1] if emails_list else None
                        except Exception:
                            pass
                content = "\n".join(text_parts)

            history_serialized.append({"role": role, "content": str(content)})

        # ── 2. Carrega contexto de negócio ────────────────────────────────────
        business_context = await BusinessContextService.get_tenant_context()
        biz_data_str = json.dumps(business_context, indent=2, ensure_ascii=False) if business_context else "{}"

        # ── 3. Monta snapshot de estado para o LLM ───────────────────────────
        has_pending = bool(crm_snapshot["pending_activities"])
        pending_str = json.dumps(crm_snapshot["pending_activities"], ensure_ascii=False) if has_pending else "nenhuma"
        contacts_str = json.dumps(crm_snapshot["contacts"], ensure_ascii=False) if crm_snapshot["contacts"] else "nenhum com canal"

        # Extrai entryId do último email para forçar reply na thread
        last_email_entry_id = None
        last_email_subject = None
        if crm_snapshot.get("last_email"):
            last_email_entry_id = crm_snapshot["last_email"].get("entryId") or crm_snapshot["last_email"].get("entry_id")
            last_email_subject = crm_snapshot["last_email"].get("subject", "")

        today = datetime.now().strftime("%A, %d/%m/%Y")

        email_thread_rule = (
            f"REGRA CRÍTICA DE EMAIL: Há uma thread ativa com este contato (último email: \"{last_email_subject}\", "
            f"entryId='{last_email_entry_id}'). Qualquer ação de email DEVE usar email_reply com "
            f"entry_id='{last_email_entry_id}'. PROIBIDO usar email_send — isso quebraria a thread do Outlook."
            if last_email_entry_id else
            "Não há thread de email anterior. Se sugerir email, use email_send com destinatário real."
        )

        system_prompt = f"""Você é o Diretor Comercial B2B e Coach de Vendas Sênior da J.Ferres.
Sua missão: analisar TODO o contexto disponível e gerar um conjunto COMPLETO e PERSONALIZADO de próximos passos.

## CONTEXTO DA J.FERRES:
{biz_data_str}

## FERRAMENTAS DISPONÍVEIS PARA O AGENTE (use nos prompts das ações):
- whatsapp_send_message: envia WhatsApp (contact, phone, message, org_name)
- email_send: envia email NOVO sem thread existente (to, subject, body)
- email_reply: responde na thread existente do Outlook (entry_id, body) — USE ESTE quando há thread ativa
- pipedrive_create_task: cria tarefa no CRM (subject, task_type=[call|meeting|task|deadline], due_date, deal_id, org_name, note)
- pipedrive_update_deal: atualiza deal (deal_id, fields)
- pipedrive_create_note: cria nota no deal (deal_id, content)
- whatsapp_get_messages: busca histórico WhatsApp (contact, phone, org_name)
- email_get_contact_history: busca histórico email (contact_name, org_name)

## {email_thread_rule}

## ESTADO ATUAL DO CRM:
- Empresa: {crm_snapshot.get('org_name') or 'ver histórico'}
- Deal ID: {crm_snapshot.get('deal_id') or 'ver histórico'} | Etapa: {crm_snapshot.get('deal_stage') or 'desconhecida'} | Valor: {crm_snapshot.get('deal_value') or 'não informado'}
- Atividades pendentes: {pending_str}
- Contatos com canal: {contacts_str}
- Contato principal: {contact_name or 'ver histórico'} {('| Tel: ' + phone) if phone else ''}
- Hoje: {today}

## REGRAS PARA AS SUGESTÕES:
1. Gere entre 5 e 8 ações — cubra TODAS as categorias relevantes (comunicação, CRM, agendamento, estratégia)
2. Se NÃO há atividades pendentes → OBRIGATÓRIO incluir sugestão de criar tarefa de acompanhamento no Pipedrive
3. Se não há reunião agendada → sugira criar tarefa de ligação/reunião com plano de abordagem
4. Baseie CADA sugestão no contexto real do histórico — cite itens, preços, datas, objeções reais
5. Mensagens devem estar PRONTAS para envio (zero placeholders entre [colchetes])
6. Priorize WhatsApp se é o canal mais ativo, email se há thread em aberto
7. Varie os tipos: não coloque todas como WhatsApp — inclua email, tarefa CRM, atualização de deal quando fizer sentido
8. Para criar tarefas no Pipedrive, o prompt DEVE usar: pipedrive_create_task com subject='...', task_type='call' ou 'meeting', due_date='YYYY-MM-DD', deal_id={crm_snapshot.get('deal_id') or 'ID do deal'}, org_name='...'

## REGRAS PARA O CAMPO "label":
- NÃO inclua o nome do canal no label (ex: PROIBIDO "WhatsApp: Cobrar retorno", CORRETO: "Cobrar retorno da cotação de Outubro")
- O canal já é exibido separadamente na interface — o label deve descrever a AÇÃO, não o canal
- Para `tarefa_crm`: seja específico sobre O QUE a tarefa registra. PROIBIDO "Atualizar Deal [empresa]". CORRETO: "Avançar deal para etapa Proposta", "Registrar visita realizada em [data]", "Criar tarefa: ligar para [contato] até [data]"
- Para `reuniao`: indique o propósito — "Agendar reunião de apresentação", "Reagendar visita técnica cancelada"
- Máximo 55 caracteres. Sem nome de empresa no label (já aparece no contexto)

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
