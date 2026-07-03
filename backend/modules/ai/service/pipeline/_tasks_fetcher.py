"""
Busca e filtragem de tarefas/atividades do Pipedrive para o pipeline de IA.
Extraído de data_fetcher.py para manter a responsabilidade única.

_fetch_tasks mutates internal_context["today_tasks"] in-place e o retorna.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from core.observability.logging_config import get_logger

log = get_logger(__name__)


async def _fetch_tasks(
    intent_info: dict,
    internal_context: Dict[str, Any],
    pipedrive_org_id: Optional[int],
    message: str,
) -> Dict[str, Any]:
    """
    Busca atividades/tarefas do Pipedrive com filtros inteligentes de data, usuário e etapa.

    Estratégia de coleta (3 prioridades em ordem):
        1. Agenda própria do usuário logado (done=0, user_id=me)
        2. Atividades dos negócios da etapa ativa (1 request global + filtro em memória)
        3. Atividades vinculadas à organização específica

    Após coleta, aplica:
        - Deduplicação por ID
        - Filtro de usuário (exceto se pedido explicitamente global)
        - Filtro de etapa (se deals_in_stage estiver no internal_context)
        - Filtro de data (today | tomorrow | overdue | future | all)

    Mutates internal_context["today_tasks"] e retorna internal_context.
    """
    import asyncio
    from datetime import date, timedelta

    date_f = intent_info.get("activity_date_filter", "today")
    target_company = intent_info.get("extracted_company_name")
    filter_msg = (
        f"para Empresa ID {pipedrive_org_id}" if pipedrive_org_id
        else (f"para '{target_company}'" if target_company else "Global")
    )
    log.debug("data_fetcher.tasks.started", date_filter=date_f, scope=filter_msg)

    try:
        from modules.crm.service.pipedrive_service import pipedrive_service

        today = date.today().isoformat()

        global_triggers = [
            "todo o pipedrive", "da equipe", "do time", "geral da empresa",
            "de todos os usuários", "dos vendedores", "empresa inteira",
            "visão global", "visão geral",
        ]
        msg_lower = message.lower()
        is_global_request = any(trigger in msg_lower for trigger in global_triggers)

        has_my_filter = any(me in msg_lower for me in ["meu", "minha", "pra mim", "comigo", "meus", "minhas"])
        if has_my_filter:
            is_global_request = False

        all_activities: list = []

        # Prioridade 1: agenda própria do usuário
        r_agenda = await pipedrive_service.make_request(
            "GET", f"activities?user_id={pipedrive_service.user_id}&done=0&limit=500"
        )
        if r_agenda and r_agenda.status_code == 200:
            all_activities.extend(r_agenda.json().get("data") or [])
            log.debug("data_fetcher.tasks.user_agenda", count=len(all_activities))

        # Prioridade 2: atividades dos negócios da etapa
        deals_in_stage = internal_context.get("deals_in_stage", [])
        if deals_in_stage:
            r_global = await pipedrive_service.make_request("GET", "activities?user_id=0&done=0&limit=500")
            if r_global and r_global.status_code == 200:
                global_activities = r_global.json().get("data") or []
                stage_deal_ids = {d["id"] for d in deals_in_stage}
                tasks_found = [
                    a for a in global_activities
                    if (a.get("deal_id").get("value") if isinstance(a.get("deal_id"), dict) else a.get("deal_id"))
                    in stage_deal_ids
                ]
                all_activities.extend(tasks_found)
                log.debug("data_fetcher.tasks.stage_filter", found=len(tasks_found))

                if len(tasks_found) < 5 and deals_in_stage:
                    async def _fetch_deal_acts(deal_id: int) -> list:
                        r = await pipedrive_service.make_request(
                            "GET", f"deals/{deal_id}/activities?done=0&limit=10"
                        )
                        return r.json().get("data") or [] if r and r.status_code == 200 else []

                    fallback_results = await asyncio.gather(
                        *[_fetch_deal_acts(d["id"]) for d in deals_in_stage[:10]]
                    )
                    for res in fallback_results:
                        all_activities.extend(res)

        # Prioridade 3: atividades da organização específica
        if pipedrive_org_id:
            r_org = await pipedrive_service.make_request(
                "GET", f"organizations/{pipedrive_org_id}/activities?done=0"
            )
            if r_org and r_org.status_code == 200:
                all_activities.extend(r_org.json().get("data") or [])

        # Deduplicação
        if all_activities:
            seen: set = set()
            unique: list = []
            for act in all_activities:
                act_id = act.get("id")
                if act_id and act_id not in seen:
                    seen.add(act_id)
                    unique.append(act)
            all_activities = unique
            log.debug("data_fetcher.tasks.deduplicated", total=len(all_activities))

        # Filtro por organização
        if not is_global_request:
            if pipedrive_org_id:
                all_activities = [
                    a for a in all_activities
                    if str(a.get("org_id").get("value") if isinstance(a.get("org_id"), dict) else a.get("org_id"))
                    == str(pipedrive_org_id)
                ]
            elif target_company and target_company.lower() not in ["null", "none"]:
                all_activities = [
                    a for a in all_activities
                    if target_company.lower() in str(a.get("org_name", "")).lower()
                ]

        tasks_to_return: list = []

        if all_activities:
            # Somente tarefas com deal_id (vinculadas a negócios)
            initial_count = len(all_activities)
            all_activities = [
                a for a in all_activities
                if (a.get("deal_id").get("value") if isinstance(a.get("deal_id"), dict) else a.get("deal_id"))
            ]
            if len(all_activities) < initial_count:
                log.debug("data_fetcher.tasks.no_deal_removed", removed=initial_count - len(all_activities))

            # Filtro de etapa
            if deals_in_stage:
                stage_deal_ids = {d.get("id") for d in deals_in_stage}
                all_activities = [
                    a for a in all_activities
                    if (a.get("deal_id").get("value") if isinstance(a.get("deal_id"), dict) else a.get("deal_id"))
                    in stage_deal_ids
                ]
                log.debug("data_fetcher.tasks.stage_filtered", kept=len(all_activities))

            # Filtro de usuário
            if not is_global_request:
                target_id = str(pipedrive_service.user_id)
                user_filtered = []
                for act in all_activities:
                    u1 = act.get("user_id") or {}
                    u1_id = str(u1.get("value") if isinstance(u1, dict) else u1)
                    u1_name = str(u1.get("name", "")).lower() if isinstance(u1, dict) else ""
                    u2 = act.get("assigned_to_user_id") or {}
                    u2_id = str(u2.get("value") if isinstance(u2, dict) else u2)
                    u2_name = str(u2.get("name", "")).lower() if isinstance(u2, dict) else ""
                    is_me = (
                        u1_id == target_id or u2_id == target_id
                        or "joao" in u1_name or "luccas" in u1_name
                        or "joao" in u2_name or "luccas" in u2_name
                    )
                    if is_me:
                        user_filtered.append(act)
                all_activities = user_filtered

            # Filtro de data
            date_filter = intent_info.get("activity_date_filter", "today")
            today_date = date.today()
            tomorrow_date = today_date + timedelta(days=1)

            for act in all_activities:
                due = act.get("due_date")
                if not due:
                    if date_filter == "all":
                        tasks_to_return.append(act)
                    continue
                due_date = date.fromisoformat(due)
                if date_filter == "today" and due_date == today_date:
                    tasks_to_return.append(act)
                elif date_filter == "tomorrow" and due_date == tomorrow_date:
                    tasks_to_return.append(act)
                elif date_filter == "overdue" and due_date < today_date:
                    tasks_to_return.append(act)
                elif date_filter == "future" and due_date >= today_date:
                    tasks_to_return.append(act)
                elif date_filter in ("all", None, ""):
                    tasks_to_return.append(act)

        internal_context["today_tasks"] = tasks_to_return
        log.info("data_fetcher.tasks.done", count=len(tasks_to_return), filter=date_f)

    except Exception as e:
        log.warning("data_fetcher.tasks.failed", error=str(e))

    return internal_context
