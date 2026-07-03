"""
modules.agent.service.core.loop_utils
=====================================
Funções utilitárias auxiliares para o loop do agente.
"""
from __future__ import annotations
import json
import ast

def _suggest_actions_done(messages: list) -> bool:
    """Retorna True se suggest_next_actions foi efetivamente executada com sucesso desde a última mensagem (real) do usuário."""
    for msg in reversed(messages):
        content = msg.get("content", "")
        # Se for string em uma mensagem do usuário, é a mensagem inicial, podemos parar
        if msg.get("role") == "user" and isinstance(content, str):
            break
            
        if isinstance(content, list):
            has_text_block = False
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        has_text_block = True
                    if block.get("type") == "tool_result" and block.get("tool_name") == "suggest_next_actions":
                        res_content = str(block.get("content", ""))
                        if "SKIPPED" not in res_content and "Erro" not in res_content:
                            return True
            # Se for uma mensagem do usuário com bloco de texto (ex: texto + imagens), também é mensagem real
            if msg.get("role") == "user" and has_text_block:
                break
                
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


def _has_non_empty_content(msg: dict) -> bool:
    """Retorna True se a mensagem tiver conteúdo não-vazio."""
    content = msg.get("content", "")
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        return len(content) > 0
    return False


def _sanitize_messages(messages: list) -> list:
    """
    Remove mensagens com conteúdo vazio e corrige turnos consecutivos com o mesmo role.

    Problemas que resolve:
    1. {"role": "user", "content": []} — mensagem vazia que faz o adaptador Gemini pular a
       mensagem, resultando em dois turnos "model" consecutivos e um erro 400 da API.
    2. Dois blocos "assistant" consecutivos que surgem quando um messages_snapshot corrompido
       de uma execução anterior é re-injetado na mensagem de retomada.

    Estratégia de merge para turnos duplicados:
    - user + user → merge dos conteúdos
    - assistant + assistant → merge dos conteúdos (preserva todos os tool_use blocks)
    """
    # 1. Remove mensagens completamente vazias (mas preserve a 1ª do histórico)
    cleaned: list = []
    for msg in messages:
        if _has_non_empty_content(msg):
            cleaned.append(msg)
        # else: descarta silenciosamente — não afeta o fluxo

    # 2. Merge de turnos consecutivos com o mesmo role
    merged: list = []
    for msg in cleaned:
        if merged and merged[-1]["role"] == msg["role"]:
            # Funde o conteúdo da mensagem duplicada na anterior
            prev = merged[-1]
            prev_content = prev.get("content", [])
            curr_content = msg.get("content", [])

            if isinstance(prev_content, str) and isinstance(curr_content, str):
                prev["content"] = prev_content + "\n" + curr_content
            elif isinstance(prev_content, list) and isinstance(curr_content, list):
                # Evita blocos tool_use duplicados (mesmo id)
                existing_ids = {b.get("id") for b in prev_content if isinstance(b, dict) and "id" in b}
                for block in curr_content:
                    if isinstance(block, dict) and block.get("id") in existing_ids:
                        continue
                    prev_content.append(block)
                prev["content"] = prev_content
            elif isinstance(prev_content, list) and isinstance(curr_content, str):
                if curr_content.strip():
                    prev_content.append({"type": "text", "text": curr_content})
                prev["content"] = prev_content
            elif isinstance(prev_content, str) and isinstance(curr_content, list):
                text_blocks = [b for b in curr_content if isinstance(b, dict) and b.get("type") == "text"]
                if text_blocks:
                    prev["content"] = prev_content + "\n" + " ".join(b.get("text", "") for b in text_blocks)
            # else: mantém o estado anterior (edge case improvável)
        else:
            merged.append(dict(msg))  # cópia rasa para não mutar o original

    return merged
