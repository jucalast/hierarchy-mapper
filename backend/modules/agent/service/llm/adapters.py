"""
modules.agent.service.llm.adapters
==================================
Conversores de formato de mensagens e ferramentas entre providers LLM.

Cada provider usa representacao diferente de tool calls e historico.
Este modulo normaliza para o formato interno e converte na resposta.

Funcoes por provider:
    OpenAI/Groq  -> _tools_to_openai, _messages_to_openai, _response_from_openai
    Gemini       -> _tools_to_gemini, _messages_to_gemini, _response_from_gemini
    Ollama       -> _messages_to_ollama_native
"""
from __future__ import annotations
import json
import uuid
from typing import Any


def _tools_to_openai(tools: list) -> list:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for t in tools
    ]


def _messages_to_ollama_native(system: str, messages: list) -> list:
    """Converte histórico interno para o formato nativo /api/chat do Ollama."""
    result = [{"role": "system", "content": system}]
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if role == "assistant":
            text_parts = []
            tool_calls = []
            if isinstance(content, list):
                for b in content:
                    if b.get("type") == "text":
                        text_parts.append(b.get("text", ""))
                    elif b.get("type") == "tool_use":
                        tool_calls.append({
                            "function": {
                                "name": b["name"],
                                "arguments": b["input"] if isinstance(b["input"], dict) else {},
                            }
                        })
            elif isinstance(content, str):
                text_parts.append(content)
            entry: dict = {"role": "assistant", "content": " ".join(text_parts)}
            if tool_calls:
                entry["tool_calls"] = tool_calls
            result.append(entry)
        elif role == "user":
            if isinstance(content, list):
                for b in content:
                    if b.get("type") == "tool_result":
                        raw = b["content"]
                        result.append({
                            "role": "tool",
                            "content": json.dumps(raw) if isinstance(raw, (dict, list)) else str(raw),
                        })
                    elif b.get("type") == "text":
                        result.append({"role": "user", "content": b["text"]})
            else:
                result.append({"role": "user", "content": str(content)})
    return result


def _messages_to_openai(messages: list) -> list:
    """Converte o histórico interno para o formato de Chat Completion da OpenAI/Groq."""
    result = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if role == "assistant":
            text_parts = []
            tool_calls = []
            if isinstance(content, list):
                for b in content:
                    if b.get("type") == "text":
                        text_parts.append(b.get("text", ""))
                    elif b.get("type") == "tool_use":
                        tool_calls.append({
                            "id": b["id"],
                            "type": "function",
                            "function": {
                                "name": b["name"],
                                "arguments": json.dumps(b["input"])
                            }
                        })
            elif isinstance(content, str):
                text_parts.append(content)

            res = {"role": "assistant", "content": " ".join(text_parts) if text_parts else None}
            if tool_calls:
                res["tool_calls"] = tool_calls
            result.append(res)

        elif role == "user":
            if isinstance(content, list):
                # Pode conter tool_result
                for b in content:
                    if b.get("type") == "tool_result":
                        result.append({
                            "role": "tool",
                            "tool_call_id": b["tool_use_id"],
                            "content": json.dumps(b["content"]) if isinstance(b["content"], (dict, list)) else str(b["content"])
                        })
                    elif b.get("type") == "text":
                        result.append({"role": "user", "content": b["text"]})
            else:
                result.append({"role": "user", "content": str(content)})

    return result


def _response_from_openai(resp: dict) -> dict:
    choice = (resp.get("choices") or [{}])[0]
    msg = choice.get("message", {})
    finish = choice.get("finish_reason", "stop")

    content = []
    if msg.get("content"):
        content.append({"type": "text", "text": msg["content"]})
    for tc in (msg.get("tool_calls") or []):
        func = tc.get("function", {})
        try:
            inp = json.loads(func.get("arguments", "{}"))
        except Exception:
            inp = {}
        content.append({
            "type": "tool_use",
            "id": tc.get("id", f"call_{uuid.uuid4().hex[:8]}"),
            "name": func.get("name", ""),
            "input": inp,
        })

    return {
        "content": content,
        "stop_reason": "tool_use" if finish == "tool_calls" else "end_turn",
    }


def _tools_to_gemini(tools: list) -> list:
    funcs = []
    for t in tools:
        funcs.append({
            "name": t["name"],
            "description": t.get("description", ""),
            "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
        })
    return [{"functionDeclarations": funcs}]


def _messages_to_gemini(messages: list) -> list:
    result = []
    for msg in messages:
        role = msg["role"]
        gemini_role = "model" if role == "assistant" else "user"
        content = msg["content"]

        parts = []
        if isinstance(content, str):
            parts.append({"text": content})
        elif isinstance(content, list):
            for b in content:
                if b.get("type") == "text":
                    text_val = b.get("text", "").strip()
                    if text_val:
                        parts.append({"text": text_val})
                elif b.get("type") == "tool_use":
                    parts.append({
                        "functionCall": {
                            "name": b.get("name", ""),
                            "args": b.get("input") or {}
                        }
                    })
                elif b.get("type") == "tool_result":
                    tc = b.get("content", "{}")
                    try:
                        tc_dict = json.loads(tc) if isinstance(tc, str) else tc
                    except Exception:
                        tc_dict = {"result": str(tc)}
                    # Gemini exige que functionResponse.response seja um dict (objeto JSON)
                    if not isinstance(tc_dict, dict):
                        tc_dict = {"output": str(tc_dict)}
                    parts.append({
                        "functionResponse": {
                            "name": b.get("tool_name", "unknown_tool"),
                            "response": tc_dict
                        }
                    })

        if parts:
            result.append({"role": gemini_role, "parts": parts})
    return result


def _response_from_gemini(resp: dict) -> dict:
    candidates = resp.get("candidates", [])
    if not candidates:
        return {"content": [], "stop_reason": "end_turn"}

    parts = candidates[0].get("content", {}).get("parts", [])

    content = []
    for part in parts:
        if "text" in part:
            content.append({"type": "text", "text": part["text"]})
        elif "functionCall" in part:
            call = part["functionCall"]
            content.append({
                "type": "tool_use",
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "name": call.get("name", ""),
                "input": call.get("args", {}),
            })

    stop_reason = "tool_use" if any(c["type"] == "tool_use" for c in content) else "end_turn"

    return {
        "content": content,
        "stop_reason": stop_reason,
    }
