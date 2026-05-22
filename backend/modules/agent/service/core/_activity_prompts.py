"""
modules.agent.service.core._activity_prompts
=============================================
Helpers de geração de prompts para atividades do CRM Pipedrive.

Extraídos de loop.py para isolar a lógica de montagem de roteiros
determinísticos por tipo de atividade.

    _dispatch_activity_etapas  — mapeia subject → roteiro de etapas (string)
    _build_task_action_prompt  — monta prompt completo para execução de tarefa
"""
from __future__ import annotations

def _dispatch_activity_etapas(subject: str, act_id, org_pd_id, deal_id) -> str:
    """
    Dispatcher de etapas: mapeia o subject da atividade do Pipedrive para um
    roteiro de execução determinístico. Evita que o LLM deduza o que fazer a
    partir do texto livre e caia em ações erradas (ex: criar tarefa ao invés
    de buscar contato).

    Retorna uma string com a seção ETAPAS_SUGERIDAS a ser injetada no prompt,
    ou string vazia para atividades sem mapeamento (o agente raciocina livre).
    """
    s = subject.lower()

    # ── Busca / encontrar contato ──────────────────────────────────────────
    _contact_search_keys = [
        "procurar contato", "encontrar contato", "conseguir contato",
        "buscar contato", "achar contato", "identificar contato",
        "localizar contato", "contato na rodada", "rodada de negócios",
    ]
    if any(k in s for k in _contact_search_keys):
        _act_args = f"org_id={org_pd_id}" + (f", deal_id={deal_id}" if deal_id else "") + f", activity_id={act_id}"
        return (
            f"ETAPAS PARA ESTA ATIVIDADE (siga nesta ordem):\n"
            f"  1. pipedrive_get_persons → verificar se já existe contato com canal (telefone ou e-mail) no CRM\n"
            f"  2a. SE existe contato com canal disponível → execute a comunicação adequada e apresente ao João\n"
            f"  2b. SE não existe contato ou está sem canal válido → open_hierarchy_drawer({_act_args})\n"
            f"      (O mapeador será aberto na UI; aguarde a conclusão antes de continuar)\n"
            f"⛔ PROIBIDO: NÃO use pipedrive_create_task — esta atividade já existe no CRM (id={act_id}).\n\n"
        )

    # ── Cobrar retorno / follow-up ─────────────────────────────────────────
    _followup_keys = [
        "cobrar retorno", "cobrar resposta", "follow", "acompanhamento",
        "follow-up", "retorno", "dar retorno", "verificar retorno",
    ]
    if any(k in s for k in _followup_keys):
        return (
            f"ETAPAS PARA ESTA ATIVIDADE (siga nesta ordem):\n"
            f"  1. pipedrive_get_persons → identificar contato com canal (telefone + e-mail)\n"
            f"  2. pipedrive_get_deals(org_id={org_pd_id}) → contexto do negócio (valor, etapa, histórico)\n"
            f"  3a. whatsapp_get_messages(contact, phone, org_name) → histórico WhatsApp\n"
            f"  3b. email_get_contact_history(contact_name, contact_email, org_name) → histórico e-mail\n"
            f"      ⚠️ OBRIGATÓRIO executar AMBAS as buscas (3a E 3b) mesmo que já tenha uma delas.\n"
            f"      O gerador de mensagem usa TODO o histórico combinado — nunca pule o e-mail.\n"
            f"  4. generate_sales_message(goal='cobrar retorno da proposta/cotação') → rascunho estratégico\n"
            f"      (usa automaticamente tudo que foi coletado nos passos anteriores)\n"
            f"  5. whatsapp_send_message OU email_reply/email_send → apresente ao João ANTES de enviar\n"
            f"      Canal preferencial: WhatsApp se tiver histórico ativo; e-mail se o último contato foi por e-mail.\n"
            f"  6. pipedrive_update_task(activity_id={act_id}, done=true) → marcar concluído após aprovação\n"
            f"⛔ PROIBIDO: NÃO crie nova tarefa — use pipedrive_update_task na atividade {act_id}.\n"
            f"⛔ PROIBIDO: NÃO gere a mensagem sem antes executar AMBAS as buscas de histórico (3a e 3b).\n\n"
        )

    # ── Agendar reunião ────────────────────────────────────────────────────
    _meeting_keys = [
        "agendar reunião", "agendar meeting", "marcar reunião",
        "agendar visita", "marcar visita", "agendar apresentação",
    ]
    if any(k in s for k in _meeting_keys):
        return (
            f"ETAPAS PARA ESTA ATIVIDADE (siga nesta ordem):\n"
            f"  1. pipedrive_get_persons → identificar decisor com canal disponível\n"
            f"  2. pipedrive_get_deals → contexto do negócio em andamento\n"
            f"  3. generate_sales_message(goal='agendar reunião/visita') → proposta personalizada\n"
            f"  4. whatsapp_send_message / email_send → apresente ao João ANTES de enviar\n"
            f"  5. pipedrive_update_task(activity_id={act_id}, done=true) → marcar concluído após aprovação\n\n"
        )

    # ── Orçamento / cotação / proposta ─────────────────────────────────────
    _quote_keys = [
        "realizar orçamento", "enviar orçamento", "fazer orçamento",
        "cotação", "proposta comercial", "enviar proposta",
    ]
    if any(k in s for k in _quote_keys):
        return (
            f"ETAPAS PARA ESTA ATIVIDADE (siga nesta ordem):\n"
            f"  1. pipedrive_get_persons → identificar contato responsável pela compra\n"
            f"  2. pipedrive_get_deals → detalhes do negócio (produto, volume, histórico)\n"
            f"  3. generate_sales_message(goal='enviar orçamento/cotação') → mensagem personalizada\n"
            f"  4. email_send / whatsapp_send_message → apresente ao João ANTES de enviar\n"
            f"  5. pipedrive_update_task(activity_id={act_id}, done=true) → marcar concluído após aprovação\n\n"
        )

    # ── Ligar / ligação / call ─────────────────────────────────────────────
    _call_keys = [
        "ligar", "realizar ligação", "fazer ligação", "ligar para",
        "ligação", "telefonar", "call",
    ]
    if any(k in s for k in _call_keys):
        return (
            f"ETAPAS PARA ESTA ATIVIDADE (siga nesta ordem):\n"
            f"  1. pipedrive_get_persons → obter número de telefone REAL do CRM (nunca invente)\n"
            f"  2. generate_call_script(contact_name, phone) → roteiro da ligação\n"
            f"  3. Apresente ao João o roteiro e o número confirmado para aprovação\n"
            f"  4. pipedrive_update_task(activity_id={act_id}, done=true) → marcar após execução\n"
            f"⛔ PROIBIDO: nunca invente ou assuma um número de telefone — use APENAS o retornado pelo CRM.\n\n"
        )

    # ── Enviar mensagem / mensagem inicial ─────────────────────────────────
    _msg_keys = [
        "enviar mensagem", "mandar mensagem", "primeira mensagem",
        "abordar", "abordagem inicial", "primeiro contato",
    ]
    if any(k in s for k in _msg_keys):
        return (
            f"ETAPAS PARA ESTA ATIVIDADE (siga nesta ordem):\n"
            f"  1. pipedrive_get_persons → contato com canal disponível\n"
            f"  2. pipedrive_get_deals / pipedrive_get_activities → contexto do negócio\n"
            f"  3. generate_sales_message(goal='primeira abordagem') → mensagem personalizada\n"
            f"  4. whatsapp_send_message / email_send → apresente ao João ANTES de enviar\n"
            f"  5. pipedrive_update_task(activity_id={act_id}, done=true) → marcar concluído após aprovação\n\n"
        )

    # Sem mapeamento — agente raciocina livremente
    return ""


def _build_task_action_prompt(act_id, subject: str, org: str, org_pd_id, deal_id, act_type: str, note: str) -> str:
    """Gera um prompt inteligente e contextualizado para cada tipo de atividade do Pipedrive."""
    _note_hint = f" (nota: {note})" if note else ""

    # Sem nome de empresa — passa o org_id/deal_id como contexto para o agente raciocinar
    if not org:
        _ctx = f"org_id={org_pd_id}" if org_pd_id else (f"deal_id={deal_id}" if deal_id else "sem empresa vinculada")
        _note_ctx = f"\nNota: {note}" if note else ""
        return (
            f"Você é o assistente comercial de João Luccas (vendedor da J.Ferres).\n\n"
            f"ATIVIDADE #{act_id} A EXECUTAR: {subject}\n"
            f"Contexto CRM: {_ctx}{_note_ctx}\n\n"
            f"Raciocine sobre o que a tarefa requer e use as ferramentas disponíveis para executá-la.\n"
            f"Para ações externas (envios, marcar como concluído), apresente o resultado ao João e aguarde aprovação."
        )

    _org_hint = f"\nEmpresa: {org} (org_id={org_pd_id})" if org_pd_id else f"\nEmpresa: {org}"
    _deal_hint_full = f"\nDeal: #{deal_id}" if deal_id else ""
    _note_hint_full = f"\nNota: {note}" if note else ""

    # Dispatcher: etapas específicas por tipo de atividade
    _etapas = _dispatch_activity_etapas(subject, act_id, org_pd_id, deal_id)

    return (
        f"Você é o assistente comercial de João Luccas (vendedor da J.Ferres).\n"
        f"O cliente é '{org}' — nunca confunda com a J.Ferres.\n\n"
        f"ATIVIDADE #{act_id} A EXECUTAR: {subject}"
        f"{_org_hint}{_deal_hint_full}{_note_hint_full}\n\n"
        f"{_etapas}"
        f"FERRAMENTAS DISPONÍVEIS:\n"
        f"  • pipedrive_get_org / pipedrive_get_persons / pipedrive_get_deals / pipedrive_get_activities\n"
        f"  • whatsapp_get_messages / email_get_contact_history\n"
        f"  • open_hierarchy_drawer (org_name, org_id, deal_id, activity_id)\n"
        f"  • generate_call_script (contact_name, phone)\n"
        f"  • generate_sales_message\n"
        f"  • email_send / whatsapp_send_message\n"
        f"  • pipedrive_update_task / pipedrive_get_activities\n"
        f"  • web_search_external\n\n"
        f"REGRAS:\n"
        f"  • Use apenas dados reais retornados pelas ferramentas — nunca invente nomes, números ou histórico\n"
        f"  • Para ações externas (enviar mensagem, marcar concluído), apresente ao João e aguarde aprovação\n"
        f"  • Não marque a atividade #{act_id} como concluída a menos que seja o objetivo explícito da tarefa\n\n"
        f"Execute agora, começando pelo raciocínio sobre o que a tarefa requer."
    )

