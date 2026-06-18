"""
modules.agent.service.core.loop_utils
=====================================
Funções utilitárias auxiliares para o loop do agente.
"""
from __future__ import annotations
import json
import ast

def _suggest_actions_done(messages: list) -> bool:
    """Retorna True se suggest_next_actions foi efetivamente executada com sucesso desde a última mensagem do usuário."""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            break
        content = msg.get("content", "")
        if isinstance(content, list):
            for block in content:
                if block.get("type") == "tool_result" and block.get("tool_name") == "suggest_next_actions":
                    res_content = str(block.get("content", ""))
                    if "SKIPPED" not in res_content and "Erro" not in res_content:
                        return True
    return False


def _extract_json_objects(text: str) -> list[str]:
    """Extrai objetos JSON balanceados (suporta aninhamento) do texto."""
    results, depth, start = [], 0, -1
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start >= 0:
                results.append(text[start:i + 1])
                start = -1
    return results


def _is_pinned(msg: dict, pinned_tools: set[str]) -> bool:
    """Retorna True se a mensagem contiver alguma chamada ou resultado das ferramentas fixadas (pinned)."""
    content = msg.get("content", "")
    if isinstance(content, str):
        content_trimmed = content.strip()
        if content_trimmed.startswith("[") or content_trimmed.startswith("{"):
            try:
                content = json.loads(content_trimmed)
            except Exception:
                try:
                    content = ast.literal_eval(content_trimmed)
                except Exception:
                    pass
    if not isinstance(content, list):
        return False
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "tool_use" and item.get("name") in pinned_tools:
            return True
        if item.get("tool_name") in pinned_tools:
            return True
    return False


def _prune_messages(messages: list, pinned_tools: set[str], max_len: int = 40) -> list:
    """Executa corte inteligente de histórico de mensagens preservando mensagens fixadas e recentes."""
    if len(messages) > max_len:
        pinned = [m for m in messages[1:-20] if _is_pinned(m, pinned_tools)]
        recent = messages[-20:]
        pinned_set = set(id(m) for m in pinned)
        return [messages[0]] + pinned + [m for m in recent if id(m) not in pinned_set]
    return messages
