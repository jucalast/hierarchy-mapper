"""
modules.agent.service.core.thread_memory
=========================================
Memória persistente de chamadas de ferramentas por thread.

Garante que o agente nunca busque o mesmo dado duas vezes na mesma conversa,
mesmo que a busca anterior tenha ocorrido em uma mensagem (e portanto execução
do loop) completamente diferente do usuário. O histórico enviado pelo frontend
a cada mensagem é truncado (últimas mensagens renderizadas, sem os blocos
estruturados de tool_use/tool_result) — por isso a deduplicação não pode
depender apenas do que vem em `history`; ela precisa olhar para os eventos
persistidos de TODA a thread no banco.
"""
from __future__ import annotations
from typing import Any, Dict, List

from core.observability.logging_config import get_logger

log = get_logger(__name__)

# Tools cujo resultado é estável para a empresa/organização inteira durante a thread
# (não dependem de qual contato específico foi consultado). batch_communication_search
# entra aqui porque varre TODOS os contatos da empresa de uma vez (e o chat já é
# escopado a uma única org por thread) — uma segunda chamada não traria nada novo.
GLOBAL_DEDUP_TOOLS = {
    "pipedrive_get_org", "pipedrive_get_persons",
    "pipedrive_get_deals", "pipedrive_get_activities",
    "batch_communication_search",
}
# Tools cujo resultado depende do contato consultado — a chave de dedup precisa incluí-lo.
CONTACT_DEDUP_TOOLS = {"whatsapp_get_messages", "email_get_contact_history"}

DEDUP_TOOLS = GLOBAL_DEDUP_TOOLS | CONTACT_DEDUP_TOOLS

# Tamanho máximo do conteúdo cacheado por chamada — mesmo teto já usado ao alimentar
# o LLM dentro de uma única execução (ver loop_executor._sanitize_result + truncamento).
_MAX_CACHED_CONTENT = 4000


def dedup_key_for(tool_name: str, tool_args: dict) -> str | None:
    """Retorna a chave de deduplicação para a chamada, ou None se a tool não for elegível."""
    if tool_name in GLOBAL_DEDUP_TOOLS:
        return tool_name
    if tool_name in CONTACT_DEDUP_TOOLS:
        contact = (
            (tool_args or {}).get("contact")
            or (tool_args or {}).get("contact_name")
            or (tool_args or {}).get("org_name")
            or ""
        ).lower().strip()
        return f"{tool_name}:{contact}"
    return None


def _iter_event_lists(msg) -> List[list]:
    """Extrai todas as listas de eventos relevantes de uma ConversationMessage: os logs
    da mensagem em si, e os logs de cada execução de ação sugerida (run) atrelada a ela."""
    lists: List[list] = []
    if isinstance(msg.logs, list):
        lists.append(msg.logs)
    data = msg.data if isinstance(msg.data, dict) else {}
    runs = data.get("suggested_actions_runs") or {}
    if isinstance(runs, dict):
        for run in runs.values():
            if isinstance(run, dict) and isinstance(run.get("logs"), list):
                lists.append(run["logs"])
    return lists


async def load_thread_tool_memory(thread_id: str | None) -> Dict[str, dict]:
    """
    Reconstrói, a partir do histórico PERSISTIDO da thread inteira, quais consultas
    (tool calls elegíveis a dedup) já foram feitas com sucesso — para que uma nova
    mensagem do usuário na mesma thread não dispare a mesma busca de novo.

    Retorna {dedup_key: {"tool": str, "summary": str, "content": str}} com o resultado
    mais recente (sucesso) de cada chamada já feita nesta thread.
    """
    memory: Dict[str, dict] = {}
    if not thread_id:
        return memory

    try:
        from core.infra.database import async_session as _async_session
        from models.conversation.conversation import ConversationMessage
        from sqlalchemy import select

        async with _async_session() as db:
            result = await db.execute(
                select(ConversationMessage)
                .where(ConversationMessage.thread_id == thread_id)
                .order_by(ConversationMessage.timestamp.asc())
            )
            msgs = result.scalars().all()

        for msg in msgs:
            for event_list in _iter_event_lists(msg):
                for ev in event_list:
                    if not isinstance(ev, dict) or ev.get("type") != "tool_result" or not ev.get("ok"):
                        continue
                    tool_name = ev.get("tool") or ev.get("tool_name") or ""
                    tool_args = ev.get("args") or {}
                    key = dedup_key_for(tool_name, tool_args)
                    if not key:
                        continue
                    ev_data = ev.get("data") or {}
                    content = ev_data.get("cached_content") or ev.get("summary") or ""
                    # Mais recente sobrescreve — queremos sempre o último estado conhecido.
                    memory[key] = {
                        "tool": tool_name,
                        "summary": ev.get("summary") or "",
                        "content": content[:_MAX_CACHED_CONTENT] if isinstance(content, str) else content,
                    }
    except Exception as e:
        log.warning("agent.thread_memory.load_failed", thread_id=thread_id, error=str(e))

    return memory
