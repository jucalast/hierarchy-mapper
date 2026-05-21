"""
Loop principal do Agente e funções de suporte ao raciocínio.

  _generate_tool_thinking — gera texto de raciocínio quando o modelo não produz
  _build_phase_status     — constrói o status de fase da investigação
  _suggest_actions_done   — verifica se sugestões já foram emitidas
  _dispatch_activity_etapas / _build_task_action_prompt — montagem de prompts de tarefa
  _agent_loop             — loop principal de tool-calling (async generator)
"""
from __future__ import annotations
import asyncio
import json
import uuid
from typing import Any, AsyncGenerator, Dict, List

from modules.agent.service.helpers import _emit, _raw_log, _fix_corrupted_name, _get_thinking_fallback, _get_label
from modules.agent.service.sanitizers import _sanitize_result
from modules.agent.service.tools import TOOLS, execute_write_tool, get_tools_anthropic_schema
from modules.agent.service.prompts import (
    SYSTEM_PROMPT_POWERFUL, SYSTEM_PROMPT_BASIC, SYSTEM_PROMPT_DIRECT,
    SYSTEM_PROMPT_TASK_AGENT, SYSTEM_PROMPT_TASK_AGENT_BASIC,
)
from modules.agent.service.llm.caller import _call_with_tools
from modules.agent.service.core.phase_tracker import _build_phase_status
from core.observability.logging_config import get_logger

log = get_logger(__name__)

MAX_ITERATIONS = 20

# Compartilhado com runner.py — ações de escrita pendentes aguardando confirmação
_PENDING: Dict[str, Dict[str, Any]] = {}

async def _generate_tool_thinking(
    tool_name: str,
    tool_args: dict,
    messages: list,
    skip_groq: bool = False,
    skip_cerebras: bool = False,
) -> str:
    """
    Gera raciocínio narrativo DEPOIS de saber qual ferramenta será executada.
    Isso garante que o thinking seja sempre consistente com a ação real do agente.

    skip_groq=True quando o modelo principal já é Groq — evita dobrar o consumo
    de quota do Groq free tier usando Groq-8b também para thinking.

    Ordem de qualidade: Gemini Flash → Cerebras → Groq 8b (se skip_groq=False).
    Retorna "" em caso de falha — o loop usa _get_label como fallback.
    """
    from core.config import settings
    from core.infra.http_client import get_http_client

    client = get_http_client()

    # Constrói resumo estruturado: objetivo + o que cada ferramenta encontrou
    # Isso dá ao modelo de thinking um mapa claro para cross-referenciar,
    # em vez de JSON cru que ele não consegue sintetizar.
    tool_label = _get_label(tool_name, tool_args)

    user_objective = ""
    findings_lines: list[str] = []

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        # Primeira mensagem de texto do usuário = objetivo original
        # Extrai apenas a parte antes de qualquer bloco de contexto injetado ([OBRIGATÓRIO...])
        if role == "user" and isinstance(content, str) and not user_objective:
            raw = content.split("\n[OBRIGATÓRIO")[0].split("\n[ESCOPO")[0].strip()
            if raw:
                user_objective = raw[:300]

        # Resultados de ferramentas = o que foi encontrado
        elif isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                tn = item.get("tool_name", "")
                tc = str(item.get("content", ""))
                if not tn:
                    continue
                # Para ferramentas de comunicação, inclui mais linhas — o modelo
                # de thinking precisa do conteúdo real para raciocinar, não só o cabeçalho
                if tn in ("email_get_contact_history", "whatsapp_get_messages"):
                    relevant = "\n  ".join(
                        l.strip() for l in tc.split("\n")[:6] if l.strip()
                    )[:400]
                else:
                    relevant = tc.split("\n")[0].strip()[:200]
                findings_lines.append(f"• {tn}: {relevant}")

    # Mantém apenas as últimas 8 descobertas para não sobrecarregar o contexto
    findings_summary = "\n".join(findings_lines[-8:]) if findings_lines else "Nenhuma ferramenta executada ainda."

    context_prompt = (
        f"OBJETIVO: {user_objective or 'não identificado'}\n\n"
        f"ENCONTRADO ATÉ AGORA:\n{findings_summary}\n\n"
        f"PRÓXIMA AÇÃO: {tool_label} ({tool_name})"
    )

    thinking_msgs = [
        {"role": "system", "content": _TOOL_THINKING_SYSTEM},
        {"role": "user", "content": context_prompt},
    ]

    # Providers em ordem de qualidade de raciocínio (não apenas velocidade)
    candidates: list[tuple[str, str, str, str]] = []
    if settings.GEMINI_API_KEY and settings.ai_gemini_models_list:
        # Gemini tem melhor raciocínio contextual para thinking
        candidates.append((
            "gemini",
            settings.GEMINI_API_KEY,
            "",  # URL dinâmica para Gemini
            settings.ai_gemini_models_list[0],  # modelo preferencial de alta disponibilidade da lista
        ))
    if settings.CEREBRAS_API_KEY and settings.ai_cerebras_models_list and not skip_cerebras:
        candidates.append((
            "cerebras",
            settings.CEREBRAS_API_KEY,
            "https://api.cerebras.ai/v1/chat/completions",
            settings.ai_cerebras_models_list[0],
        ))
    if settings.GROQ_API_KEY and not skip_groq:
        candidates.append((
            "groq",
            settings.GROQ_API_KEY,
            "https://api.groq.com/openai/v1/chat/completions",
            "llama-3.1-8b-instant",
        ))

    for prov_name, api_key, url, model in candidates:
        _rl_key = f"{prov_name}:{model}"
        if _time.monotonic() < _agent_rate_limited_until.get(_rl_key, 0):
            continue
        try:
            if prov_name == "gemini":
                gemini_url = (
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{model}:generateContent?key={api_key}"
                )
                gemini_msgs = [
                    {"role": "user" if m["role"] != "assistant" else "model",
                     "parts": [{"text": m["content"]}]}
                    for m in thinking_msgs
                    if m["role"] != "system"
                ]
                system_text = next(
                    (m["content"] for m in thinking_msgs if m["role"] == "system"), ""
                )
                resp = await client.post(
                    gemini_url,
                    json={
                        "contents": gemini_msgs,
                        "systemInstruction": {"parts": [{"text": system_text}]},
                        "generationConfig": {"maxOutputTokens": 250, "temperature": 0.2},
                    },
                    timeout=15.0,
                )
                if resp.status_code == 200:
                    parts = (
                        resp.json()
                        .get("candidates", [{}])[0]
                        .get("content", {})
                        .get("parts", [{}])
                    )
                    text = "".join(p.get("text", "") for p in parts).strip()
                    if text:
                        return text
                if resp.status_code == 429:
                    _agent_rate_limited_until[_rl_key] = _time.monotonic() + 60
            else:
                req_payload = {
                    "model": model,
                    "max_tokens": 250,
                    "temperature": 0.2,
                    "messages": thinking_msgs
                }
                req_headers = {
                    "Authorization": f"Bearer {api_key}",
                    "content-type": "application/json"
                }
                if prov_name == "cerebras":
                    # Imposição de limite de tokens preventiva (Evita erro 429 defensivo por alocação MSL)
                    if "max_completion_tokens" not in req_payload and "max_tokens" not in req_payload:
                        req_payload["max_completion_tokens"] = 250
                    if "gpt-oss-120b" in model:
                        req_payload["reasoning_effort"] = "medium"
                    elif "zai-glm-4.7" in model:
                        req_payload["clear_thinking"] = True
                    if "service_tier" not in req_payload:
                        req_payload["service_tier"] = "auto"
                    req_headers["queue_threshold"] = "15000"
                    req_headers["Cerebras-Queue-Threshold"] = "15000"

                resp = await client.post(
                    url,
                    json=req_payload,
                    headers=req_headers,
                    timeout=15.0,
                )
                if resp.status_code == 200:
                    text = (
                        resp.json()
                        .get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                        .strip()
                    )
                    if text:
                        return text
                if resp.status_code == 429:
                    _agent_rate_limited_until[_rl_key] = _time.monotonic() + 60
        except Exception as e:
            log.warning("agent.llm.thinking_aux_error", provider=prov_name, model=model, error=str(e))
            pass

    return ""


def _build_phase_status(messages: list, query_type: str = "agent_workflow", org_id: int | None = None) -> str:
    """
    Constrói o system prompt completo para a fase atual da investigação.
    Cada fase inclui todas as instruções comportamentais relevantes para ela —
    sem enviar o que não é necessário naquele momento.
    Fase 1 ~80 tokens, Fase 2 ~120, Fase 3 ~200, Fase 4 ~150.
    Fallback: SYSTEM_PROMPT_POWERFUL completo se qualquer exceção ocorrer.
    """
    import re as _re

    today = datetime.now().strftime('%Y-%m-%d')

    # ── Extrai estado da investigação ────────────────────────────────────────
    tools_called: set[str] = set()   # todas as ferramentas já chamadas
    contacts_found: list[str] = []   # contatos encontrados no pipedrive_get_persons
    contact_phones: dict[str, str] = {} # Mapeamento nome -> telefone
    org_name: str = ""
    whatsapp_searched: set[str] = set()
    email_searched: set[str] = set()
    task_contacts: set[str] = set()  # Contatos vinculados a atividades pendentes (Prioridade Máxima)

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        # Se for string representando uma lista/dicionário, tenta parsear usando json ou ast
        if isinstance(content, str):
            content_trimmed = content.strip()
            if content_trimmed.startswith("[") or content_trimmed.startswith("{"):
                try:
                    import json as _json
                    content = _json.loads(content_trimmed)
                except Exception:
                    try:
                        import ast as _ast
                        content = _ast.literal_eval(content_trimmed)
                    except Exception:
                        pass
            
            # Fallback robusto se ainda for string simples (extração por substring)
            if isinstance(content, str):
                for t_name in [
                    "pipedrive_get_org", "pipedrive_get_persons", "pipedrive_get_deals",
                    "pipedrive_get_activities", "pipedrive_get_all_activities",
                    "whatsapp_get_messages", "email_get_contact_history",
                    "generate_call_script", "open_hierarchy_drawer", "pipedrive_create_task",
                    "generate_dossier"
                ]:
                    if t_name in content_trimmed:
                        tools_called.add(t_name)

        # ── Lê ARGS das tool_use blocks (mensagens do assistente)
        # Mais confiável que parsear o resultado — captura o que FOI pedido.
        # Também popula tools_called para rastrear fase mesmo se o tool_result for truncado.
        if role == "assistant" and isinstance(content, list):
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                tn = block.get("name", "")
                if tn:
                    tools_called.add(tn)
                args = block.get("input") or {}
                if tn == "pipedrive_get_org" and args.get("org_name"):
                    org_name = args["org_name"].strip()
                if tn == "whatsapp_get_messages" and args.get("contact"):
                    whatsapp_searched.add(args["contact"].lower())
                if tn == "email_get_contact_history":
                    name = args.get("contact_name") or args.get("org_name") or ""
                    if name:
                        email_searched.add(name.lower())

        # ── Lê RESULTADOS das tool_result blocks (mensagens do user/tool)
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict):
                continue
            tn = item.get("tool_name", "")
            tc = str(item.get("content", ""))
            if not tn:
                continue

            tools_called.add(tn)

            if tn == "pipedrive_get_org" and not org_name:
                m_sum = _re.search(r'"summary"\s*:\s*"([^|]+)\|', tc)
                if m_sum:
                    org_name = m_sum.group(1).strip()
                if not org_name:
                    m_name = _re.search(r'"name"\s*:\s*"([^"]+)"', tc)
                    if m_name:
                        org_name = m_name.group(1).strip()
                if not org_name:
                    m_org = _re.search(r'🏢 ORG:\s*([^\n\\]+)', tc)
                    if m_org:
                        org_name = m_org.group(1).strip()

            # Extrai TODOS os contatos do resultado de pipedrive_get_persons
            if tn == "pipedrive_get_persons" and not contacts_found:
                parsed_ok = False
                try:
                    import json as _json
                    data = _json.loads(tc)
                    persons_list = data.get("persons", []) if isinstance(data, dict) else []
                    for p in persons_list:
                        if isinstance(p, dict) and p.get("name"):
                            name = p["name"].strip()
                            name_lower = name.lower()
                            is_company = any(suffix in name_lower for suffix in [
                                "gmbh", "ltda", "s.a", "sa", "participaco", "participaço", 
                                "holding", "corp", "s/a", "industria", "indústria", 
                                "comercio", "comércio", "servico", "serviço", "eireli", 
                                "me", "epp", "grupo"
                            ])
                            if is_company:
                                continue
                            if name and name not in contacts_found:
                                contacts_found.append(name)
                                # Captura telefone se disponível
                                if p.get("phone"):
                                    contact_phones[name] = str(p["phone"]).strip()
                    parsed_ok = len(contacts_found) > 0
                except Exception:
                    pass

                if not parsed_ok:
                    import unicodedata as _uc
                    def _strip_acc(s: str) -> str:
                        return "".join(c for c in _uc.normalize("NFD", s.lower()) if _uc.category(c) != "Mn")

                    raw = tc
                    names = _re.findall(
                        r'([A-ZÁÉÍÓÚÃÕÂÊÎÔÛ][a-záéíóúãõâêîôûç]+(?:\s+[A-ZÁÉÍÓÚÃÕÂÊÎÔÛ][a-záéíóúãõâêîôûç]+)*)',
                        raw,
                    )
                    # Normaliza org_name SEM acento para comparação robusta
                    org_words_norm = set(_strip_acc(org_name or "").split())
                    for n in names:
                        n_lower = n.lower()
                        is_company = any(suffix in n_lower for suffix in [
                            "gmbh", "ltda", "s.a", "sa", "participaco", "participaço", 
                            "holding", "corp", "s/a", "industria", "indústria", 
                            "comercio", "comércio", "servico", "serviço", "eireli", 
                            "me", "epp", "grupo"
                        ])
                        if is_company:
                            continue
                        n_words_norm = set(_strip_acc(n).split())
                        stopwords_ext = {"do", "da", "de", "dos", "das", "ltda", "sa", "s.a", "cia"}
                        # Descarta se for o nome da org (comparação sem acento)
                        if not n_words_norm.issubset(org_words_norm | stopwords_ext):
                            if n not in contacts_found:
                                contacts_found.append(n)
                                # Tenta buscar telefone no entorno do nome via regex simples
                                m_ph = _re.search(rf'{_re.escape(n)}[^\n·]*?(?:\+|tel:|cel:)?\s*([\d\s\-\(\)\+]{8,20})', raw)
                                if m_ph:
                                    contact_phones[n] = m_ph.group(1).strip()
                contacts_found = contacts_found[:15]

            # Rastreia WhatsApp por resultado (fallback quando args não disponíveis)
            if tn == "whatsapp_get_messages" and not any(True for _ in []):
                m = _re.search(
                    r'(?:mensagens\s+com|com)\s+([A-Za-záéíóúãõâêîôûç][^\-·\n]{2,40})',
                    tc, _re.IGNORECASE
                )
                if m:
                    whatsapp_searched.add(m.group(1).strip().lower())

            # Rastreia email por resultado (fallback)
            if tn == "email_get_contact_history" or tn == "email_get_inbox":
                m = _re.search(
                    r'(?:e-mails?\s+(?:\w+\s+)?(?:para|encontrados\s+para)|histórico\s+para)\s+'
                    r'([A-Za-záéíóúãõâêîôûç][^\n·\(]{2,50})',
                    tc, _re.IGNORECASE
                )
                if m:
                    email_searched.add(m.group(1).strip().lower())

    # ── Helpers ──────────────────────────────────────────────────────────────
    import unicodedata as _uc2
    def _norm_acc(s: str) -> str:
        """Remove diacríticos e converte para minúsculas para comparação fuzzy."""
        return "".join(c for c in _uc2.normalize("NFD", s.lower()) if _uc2.category(c) != "Mn")

    def _searched(name: str, done: set[str]) -> bool:
        """Fuzzy match insensível a acentos — 'Ápice' == 'Apice', 'Wesley' == 'wesley'."""
        nl = _norm_acc(name)
        done_norm = {_norm_acc(d) for d in done}
        words = nl.split()
        if not words:
            return False
        return (
            nl in done_norm
            or words[0] in done_norm
            or any(words[0] in d or d in nl for d in done_norm)
        )

    # ── Determina fase ───────────────────────────────────────────────────────
    if "pipedrive_get_all_activities" in tools_called:
        tools_called.add("pipedrive_get_activities")
        
    _pd_required = {"pipedrive_get_org", "pipedrive_get_persons",
                    "pipedrive_get_deals", "pipedrive_get_activities"}
    pipedrive_complete = _pd_required.issubset(tools_called)

    # ── OTIMIZAÇÃO DE TOKENS E ITERAÇÕES (FOCO NO CONTATO ATIVO & RECOMENDAÇÕES) ──
    active_contacts = set()
    referred_contacts = set()

    def _extract_referrals(text: str) -> list[str]:
        import re
        if not text:
            return []
        # Padrões para detectar indicações: "fale com X", "cobrar retorno com X", etc.
        # Versão simplificada e agressiva: pega qualquer coisa que venha depois de um verbo de ação comercial
        # até encontrar o primeiro nome Capitalizado, ignorando aspas, espaços ou símbolos intermediários.
        patterns = [
            r'(?:fale|falar|tratar|contato|chame|procure|indico|indicação|recomendo|conversar|follow-up|cobrar|acompanhar|retorno|atender|responder)[^A-ZÁÉÍÓÚÃÕÂÊÎÔÛç]*([A-ZÁÉÍÓÚÃÕÂÊÎÔÛç][a-záéíóúãõâêîôûç]+(?:\s+[A-ZÁÉÍÓÚÃÕÂÊÎÔÛç][a-záéíóúãõâêîôûç]+)?)',
            r'(?:contato|com)\s+[^A-ZÁÉÍÓÚÃÕÂÊÎÔÛç]*([A-ZÁÉÍÓÚÃÕÂÊÎÔÛç][a-záéíóúãõâêîôûç]+(?:\s+[A-ZÁÉÍÓÚÃÕÂÊÎÔÛç][a-záéíóúãõâêîôûç]+)?)'
        ]
        referrals = []
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for m in matches:
                name = m.strip()
                # Descarta termos comuns de negócio capturados acidentalmente
                if len(name) > 2 and name.lower() not in ['para', 'como', 'esta', 'esse', 'essa', 'quem', 'onde', 'quando', 'porque', 'orçamento', 'financeiro', 'comercial', 'compras', 'vendas', 'diretor', 'gerente', 'negócio', 'parceiro', 'empresa', 'cliente', 'retorno', 'pedido', 'analise', 'execute', 'seguinte', 'atividade']:
                    if name not in referrals:
                        referrals.append(name)
        return referrals

    def _is_referred(contact_name: str, referred_names: set[str]) -> bool:
        cn_norm = _norm_acc(contact_name)
        cn_words = set(cn_norm.split())
        for r in referred_names:
            r_norm = _norm_acc(r)
            r_words = set(r_norm.split())
            if r_norm in cn_norm or cn_norm in r_norm or (r_words and r_words.issubset(cn_words)) or (cn_words and cn_words.issubset(r_words)):
                return True
        return False

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        # Se for string representando uma lista/dicionário, tenta parsear usando json ou ast
        if isinstance(content, str):
            content_trimmed = content.strip()
            if content_trimmed.startswith("[") or content_trimmed.startswith("{"):
                try:
                    import json as _json
                    content = _json.loads(content_trimmed)
                except Exception:
                    try:
                        import ast as _ast
                        content = _ast.literal_eval(content_trimmed)
                    except Exception:
                        pass

        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                tn = item.get("tool_name", "")
                tc = str(item.get("content", ""))
                if not tn or not tc:
                    continue

                if tn in ("whatsapp_get_messages", "email_get_contact_history"):
                    c_name = None
                    try:
                        import json as _json
                        data = _json.loads(tc)
                        if isinstance(data, dict):
                            c_name = data.get("contact") or data.get("contact_name")
                        elif isinstance(data, str):
                            # Tenta extrair de "💬 WHATSAPP (Contact):"
                            m_wa = _re.search(r'💬 WHATSAPP \(([^)]+)\):', data)
                            if m_wa:
                                c_name = m_wa.group(1).strip()
                            else:
                                # Tenta extrair de "📧 HISTÓRICO EMAIL (Contact):" ou do thread extractor
                                m_em = _re.search(r'📧 HISTÓRICO EMAIL \(([^)]+)\):', data)
                                if m_em:
                                    c_name = m_em.group(1).strip()
                                else:
                                    m_em2 = _re.search(r'📧 E-mails com ([^:\n]+):', data)
                                    if m_em2:
                                        c_name = m_em2.group(1).strip()
                                    else:
                                        # Fallback geral para thread summary que pode começar com "Thread com " ou similar
                                        m_em3 = _re.search(r'(?:Thread|E-mails|Mensagens)\s+(?:com|de|para)\s+([A-Za-záéíóúãõâêîôûç\s]{2,40})', data, _re.IGNORECASE)
                                        if m_em3:
                                            c_name = m_em3.group(1).strip()
                    except Exception:
                        pass

                    if not c_name:
                        # Tenta extrair a chave "contact" ou "contact_name" do JSON (mesmo que truncado)
                        m_json_c = _re.search(r'"(?:contact|contact_name)"\s*:\s*"([^"]+)"', tc)
                        if m_json_c:
                            c_name = m_json_c.group(1).strip()
                    if not c_name:
                        m_c = _re.search(r'(?:mensagens\s+com|com|para)\s+([A-Za-záéíóúãõâêîôûç\s]{2,40})', tc, _re.IGNORECASE)
                        if m_c:
                            c_name = m_c.group(1).strip()

                    if c_name:
                        c_name_lower = c_name.lower().strip()
                        has_active = False
                        msg_count = 0
                        has_reply = False
                        
                        try:
                            import json as _json
                            import ast
                            data = None
                            try:
                                data = _json.loads(tc)
                            except Exception:
                                try:
                                    data = ast.literal_eval(tc)
                                except Exception:
                                    pass
                                    
                            if isinstance(data, dict) and data.get("ok"):
                                msg_count = data.get("count", 0)
                                if tn == "whatsapp_get_messages":
                                    messages_list = data.get("messages", []) or []
                                    has_reply = any(isinstance(m, str) and not m.startswith("[Você]") and not m.startswith("[joao.moura") for m in messages_list)
                                    if msg_count >= 10 and has_reply:
                                        has_active = True
                                elif tn == "email_get_contact_history":
                                    if msg_count >= 3:
                                        has_active = True
                            elif isinstance(data, str):
                                # Se data for a string sanitizada!
                                lines = [l.strip() for l in data.split("\n") if l.strip()]
                                chat_lines = [l for l in lines if l.startswith("[")]
                                if tn == "whatsapp_get_messages":
                                    msg_count = len(chat_lines)
                                    if msg_count == 0:
                                        m_text_count = _re.search(r'(\d+)\s*(?:mensagens|conversas)', data, _re.IGNORECASE)
                                        if m_text_count:
                                            msg_count = int(m_text_count.group(1))
                                    has_reply = any(not any(x in l for x in ["[Você]", "[EU]", "[joao.moura"]) for l in chat_lines)
                                    if (msg_count >= 10 or len(lines) >= 8) and has_reply:
                                        has_active = True
                                elif tn == "email_get_contact_history":
                                    has_reply = "sem resposta" not in data.lower() and "nenhum e-mail" not in data.lower()
                                    if has_reply:
                                        has_active = True
                        except Exception:
                            pass

                        # Fallback robusto via Regex (para JSONs truncados ou formatados incorretamente)
                        if not has_active:
                            # 1. Tenta extrair o count do JSON (mesmo que truncado)
                            m_count = _re.search(r'"count"\s*:\s*(\d+)', tc)
                            if m_count:
                                msg_count = int(m_count.group(1))
                            else:
                                # Tenta buscar padrões como "34 mensagens" ou "12 e-mails" no texto
                                m_text_count = _re.search(r'(\d+)\s*(?:mensagens|e-mails|emails|conversas)', tc, _re.IGNORECASE)
                                if m_text_count:
                                    msg_count = int(m_text_count.group(1))
                                    
                            # 2. Busca se há resposta do contato externo (que não é Você ou joao.moura)
                            has_reply = bool(_re.search(r'\[(?!Você)(?!joao\.moura)[^\]]+\]:', tc))
                            
                            if tn == "whatsapp_get_messages":
                                if msg_count >= 10 and has_reply:
                                    has_active = True
                            elif tn == "email_get_contact_history":
                                if msg_count >= 3:
                                    has_active = True

                        if not has_active:
                            # Heurística textual como fallback final de salvaguarda
                            text_lower = tc.lower()
                            if "nenhum e-mail encontrado" not in text_lower and "0 e-mails" not in text_lower and "0 mensagens" not in text_lower and "não encontrado" not in text_lower and "sem histórico" not in text_lower:
                                # Se o texto for substancial (representando conversa madura ou truncado), aceita
                                if len(tc) > 800 or "truncado" in text_lower or tc.count("\n") > 10:
                                    has_active = True

                        if has_active:
                            for c in contacts_found:
                                if _norm_acc(c) == _norm_acc(c_name) or _searched(c, {c_name_lower}) or _norm_acc(c) in _norm_acc(c_name):
                                    active_contacts.add(c)

                        for ref in _extract_referrals(tc):
                            referred_contacts.add(ref)

                elif tn == "pipedrive_get_activities":
                    # Tenta extrair nomes do JSON das atividades (person_name é o canal oficial de prioridade)
                    try:
                        import json as _json
                        data = _json.loads(tc)
                        # O retorno da tool usa a chave 'pending' (veja tools.py:exec_pipedrive_get_activities)
                        activities = data.get("pending", []) or data.get("activities", []) or data.get("data", [])
                        if not isinstance(activities, list): activities = []
                        
                        for act in activities:
                            p_name = act.get("person_name")
                            if p_name:
                                # No pending da tool, done já é False por definição (ou 0)
                                task_contacts.add(p_name)
                                referred_contacts.add(p_name)
                            # Também busca no assunto e nota da atividade
                            for ref in _extract_referrals(act.get("subject", "")):
                                referred_contacts.add(ref)
                            for ref in _extract_referrals(act.get("note", "")):
                                referred_contacts.add(ref)
                    except:
                        # Fallback para regex no texto bruto
                        for ref in _extract_referrals(tc):
                            referred_contacts.add(ref)
                
                elif tn == "pipedrive_get_org":
                    # Tenta pegar o contato principal do deal/org se estiver no JSON
                    try:
                        import json as _json
                        data = _json.loads(tc)
                        if isinstance(data, dict):
                            p_name = data.get("contact_name") or data.get("person_name")
                            if p_name:
                                referred_contacts.add(p_name)
                    except: pass

    # ── Extrai Objetivo Original (para priorizar contatos citados na tarefa)
    goal_contacts = set()
    
    # Procura o objetivo nos últimos 3 msgs de usuário (mais robusto que apenas messages[0] em histórico longo)
    user_msgs = [m for m in messages if m.get("role") == "user" and isinstance(m.get("content"), str)]
    for um in reversed(user_msgs[-3:]):
        u_content = um["content"]
        
        # 1. Extração por padrões explícitos (ex: "cobrar retorno com X")
        goal_referrals = _extract_referrals(u_content)
        for r in goal_referrals:
            goal_contacts.add(r)
            referred_contacts.add(r)
            
        # 2. Extração de todos os nomes Capitalizados no trecho do objetivo
        # Foca apenas no texto antes de tags de escopo
        clean_goal = u_content.split("\n[OBRIGATÓRIO")[0].split("\n[ESCOPO")[0].strip()
        names_in_goal = _re.findall(r'([A-ZÁÉÍÓÚÃÕÂÊÎÔÛç][a-záéíóúãõâêîôûç]+(?:\s+[A-ZÁÉÍÓÚÃÕÂÊÎÔÛç][a-záéíóúãõâêîôûç]+)?)', clean_goal)
        for n in names_in_goal:
            if n.lower() not in ["joão luccas", "j.ferres", "pipedrive", "whatsapp", "email", "linkb2b", "knorr", "bremse", "analise", "execute", "atividade"]:
                goal_contacts.add(n)
                referred_contacts.add(n)
        
        # Se encontrou nomes no objetivo, para de procurar em mensagens anteriores
        if goal_contacts:
            break

    # ── OTIMIZAÇÃO DE FILA: Prioriza (1) Citados no Goal, (2) Indicados em tarefas, (3) Ativos
    optimized_contacts = []
    
    # Passo 0: PRIORIDADE ABSOLUTA - Contatos vinculados a tarefas pendentes no CRM
    for c in contacts_found:
        if _is_referred(c, task_contacts) and c not in optimized_contacts:
            optimized_contacts.append(c)

    # Passo 1: Prioridade Alta - Contatos do objetivo (goal)
    # Primeiro os que foram extraídos via padrões explícitos (com Matheus Muniz)
    for c in contacts_found:
        if _is_referred(c, goal_contacts) and c not in optimized_contacts:
            optimized_contacts.append(c)
            
    # Passo 2: Contatos referenciados em atividades ou conversas
    for c in contacts_found:
        if _is_referred(c, referred_contacts) and c not in optimized_contacts:
            optimized_contacts.append(c)
            
    # Passo 3: Contatos que já sabemos serem ativos (têm mensagens)
    for c in contacts_found:
        if c in active_contacts and c not in optimized_contacts:
            optimized_contacts.append(c)
            
    # Passo 4: O restante (alfabético ou ordem original do Pipedrive)
    remaining_unsorted = [c for c in contacts_found if c not in optimized_contacts]
    optimized_contacts.extend(remaining_unsorted)

    # Garantia de segurança: Matheus Muniz DEVE estar no topo se citado no goal
    # Mesmo que a lista de contatos seja longa, o Passo 1 já deve ter cuidado disso.

    pending_wapp  = [c for c in optimized_contacts if not _searched(c, whatsapp_searched)]
    pending_email = [c for c in optimized_contacts if not _searched(c, email_searched)]
    org_wapp_done  = bool(org_name and _searched(org_name, whatsapp_searched))
    org_email_done = bool(org_name and _searched(org_name, email_searched))

    if active_contacts:
        comms_complete = (
            pipedrive_complete
            and not pending_wapp
            and not pending_email
        )
    else:
        comms_complete = (
            pipedrive_complete
            and not pending_wapp
            and not pending_email
            and (org_wapp_done or not org_name)
            and (org_email_done or not org_name)
        )
    dossier_done = "generate_dossier" in tools_called

    base = (
        f"Data: {today}. Agente de Investigação Comercial LinkB2B.\n"
        "REGRAS: (1) Uma ferramenta por turno — nunca duas. "
        "(2) Execute diretamente — nunca pergunte permissão. "
        "(3) whatsapp_get_messages e email_get_contact_history com o NOME DA PESSOA "
        "— NUNCA use whatsapp_list_chats ou email_get_inbox quando já tem o nome. "
        "(4) ANTES de cada ferramenta: escreva em linguagem natural o que o usuário quer, "
        "o que você já encontrou e por que esta ferramenta é o próximo passo. "
        "Cite nomes reais, datas e dados concretos do histórico. "
        "(5) CONTINUIDADE OBRIGATÓRIA (CRÍTICO): Se uma ferramenta retornar 0 resultados ou dados vazios, VOCÊ NÃO DEVE PARAR. Registre o fato e CHAME IMEDIATAMENTE a próxima ferramenta pendente na mesma resposta. NUNCA encerre seu turno apenas com comentários de texto sem chamar uma ferramenta, e NUNCA declare a tarefa como concluída se ainda houver nomes na lista 'Pendente' abaixo, a menos que todas as fases da investigação estejam 100% concluídas.\n"
        "(6) IDENTIDADE: João Luccas (joao.moura@jferres.com.br ou qualquer e-mail do domínio jferres.com.br) é o vendedor/remetente (você / o usuário do sistema). Ele NUNCA deve ser cadastrado ou sugerido como contato (person/lead) de nenhuma empresa no Pipedrive. Os contatos reais e leads são sempre os destinatários/interlocutores externos (ex: Lgustavo/Luis Gustavo).\n"
        "(7) NOME DO AGENTE (CRÍTICO): Seu nome é 'Agente de Investigação Comercial LinkB2B'. Este é o nome do seu próprio sistema/plataforma de vendas. Você está ABSOLUTAMENTE PROIBIDO de buscar informações, contatos, deals ou atividades sobre a organização 'LinkB2B', pois ela representa o seu próprio sistema, e não o cliente externo sob investigação."
    )

    # ── Tratamento Específico: Tarefas do Dia (atalho eficiente) ─────────────
    # pipedrive_tasks é mantido como fast-path porque a ação é 100% determinística.
    if query_type == "pipedrive_tasks":
        if "pipedrive_get_all_activities" not in tools_called:
            return (
                f"Data: {today}. Você é o Agente de Atendimento Comercial LinkB2B.\n"
                "O usuário quer saber o que ele tem para fazer hoje (tarefas/atividades).\n"
                "Sua PRÓXIMA FERRAMENTA deve ser obrigatoriamente: pipedrive_get_all_activities.\n"
                "Execute-a para obter a lista completa de atividades para hoje e atrasadas.\n"
                "NÃO chame nenhuma outra ferramenta antes desta. Apenas chame pipedrive_get_all_activities com um dicionário vazio {}.\n"
                "Não faça perguntas ao usuário, execute diretamente a ferramenta."
            )
        else:
            return (
                f"Data: {today}. Você é o Agente de Atendimento Comercial LinkB2B.\n"
                "As tarefas foram buscadas e os cards de ação já foram gerados automaticamente na interface. "
                "Escreva apenas uma mensagem curta e encorajadora informando quantas tarefas há para hoje e quantas estão atrasadas. "
                "NÃO chame mais ferramentas."
            )

    # ── MODO AGENTE UNIVERSAL (Copilot-style) ────────────────────────────────
    # Para QUALQUER query que NÃO seja investigação de empresa (deal_status/agent_workflow),
    # o modelo recebe um prompt universal com TODAS as ferramentas e decide sozinho.
    #
    # VANTAGEM: NÃO depende do classificador de intenções. Mesmo se o classificador
    # errar (ex: retornar "general" para "o que tenho pra fazer"), o modelo principal
    # (Claude/Gemini) é inteligente o suficiente para escolher a ferramenta certa.
    #
    # Isso é equivalente ao "agent mode" do GitHub Copilot.
    _is_investigation = query_type in ("deal_status", "agent_workflow")
    _investigation_active = bool(
        {"pipedrive_get_org", "pipedrive_get_persons", "pipedrive_get_deals", "pipedrive_get_activities"} & tools_called
    )

    if not _is_investigation and not _investigation_active:
        # ── Turnos seguintes: Detecção automática por ferramentas chamadas ──
        # Em vez de depender do classificador, detectamos o que apresentar
        # pelo que o modelo JÁ FEZ (quais ferramentas foram chamadas).
        if tools_called:
            _tool_result_map = {
                "pipedrive_get_all_activities": "tarefas e atividades de hoje e atrasadas",
                "email_get_inbox": "e-mails da caixa de entrada",
                "email_get_contact_history": "histórico de e-mails do contato",
                "whatsapp_list_chats": "conversas recentes do WhatsApp",
                "whatsapp_get_messages": "mensagens do WhatsApp",
                "web_search_external": "resultados da pesquisa na web",
                "pipedrive_get_persons": "contatos da empresa",
                "pipedrive_get_deals": "negócios/deals da empresa",
            }
            _found = [desc for tool, desc in _tool_result_map.items() if tool in tools_called]
            _what = ", ".join(_found) if _found else "dados coletados"

            return (
                f"Data: {today}. Você é o Agente Comercial LinkB2B.\n"
                f"Você já coletou: {_what}.\n"
                "Apresente os resultados de forma altamente profissional, organizada e detalhada para o usuário.\n"
                "Se o usuário fez uma pergunta específica, responda diretamente usando os dados coletados.\n"
                "Se as tarefas incluem empresas, agrupe por empresa. Se são e-mails, organize por data.\n"
                "NÃO chame mais ferramentas. Escreva apenas a resposta final."
            )

        # ── Primeiro turno: Prompt Universal com TODAS as ferramentas ──
        # O LLM analisa a mensagem e DECIDE SOZINHO qual ferramenta usar.
        return (
            f"Data: {today}. Você é o Agente Comercial LinkB2B — o parceiro de negócios inteligente do usuário.\n\n"
            "Você é um AGENTE AUTÔNOMO com acesso a ferramentas poderosas de CRM, WhatsApp e Email.\n"
            "Analise a mensagem do usuário e DECIDA SOZINHO qual ferramenta usar para responder da melhor forma.\n\n"
            "REGRAS ABSOLUTAS:\n"
            "(1) Execute diretamente — NUNCA peça permissão ou faça perguntas de confirmação.\n"
            "(2) Uma ferramenta por turno — nunca duas.\n"
            "(3) Se a pergunta pode ser respondida com dados do sistema, USE a ferramenta certa.\n"
            "(4) Se é uma saudação ou pergunta sobre o sistema, responda diretamente SEM ferramentas.\n\n"
            "FERRAMENTAS DISPONÍVEIS E QUANDO USAR CADA UMA:\n\n"
            "📋 TAREFAS E AGENDA:\n"
            "• pipedrive_get_all_activities → Para 'o que tenho pra fazer?', 'minhas tarefas', 'agenda de hoje', "
            "'o que tá pendente?', 'atividades atrasadas'. Chame com argumentos: {}\n\n"
            "🏢 CRM / EMPRESAS:\n"
            "• pipedrive_get_org → Para buscar info de uma empresa específica no CRM\n"
            "• pipedrive_get_persons → Para listar contatos/pessoas de uma empresa\n"
            "• pipedrive_get_deals → Para ver negócios/deals de uma empresa\n"
            "• pipedrive_get_activities → Para ver tarefas DE UMA empresa específica\n\n"
            "💬 WHATSAPP:\n"
            "• whatsapp_list_chats → Para 'me mostra minhas conversas', 'quem me mandou mensagem'\n"
            "• whatsapp_get_messages → Para ler mensagens de um contato específico\n\n"
            "📧 EMAIL:\n"
            "• email_get_inbox → Para 'me mostra meus emails', 'tem email novo?', 'caixa de entrada'\n"
            "• email_get_contact_history → Para buscar emails de um contato ou empresa específica\n\n"
            "🔍 PESQUISA:\n"
            "• web_search_external → Para pesquisar informações na web sobre empresas/contatos\n\n"
            "DECISÃO: Leia a mensagem do usuário, escolha a ferramenta mais adequada e execute-a imediatamente.\n"
            "Se nenhuma ferramenta for necessária (saudação, pergunta sobre o sistema), responda diretamente com "
            "uma saudação calorosa, apresente-se e diga brevemente o que pode fazer pelo usuário."
        )

    # ── Fluxo de Investigação de Empresa (deal_status / agent_workflow) ─────
    # A partir daqui, estamos em modo de investigação rígida.
    # Este fluxo NÃO foi alterado — continua funcionando exatamente como antes.
    if not tools_called:
        return base + "\n\nInício. Execute pipedrive_get_org agora."

    # ── Fase 2 — Mapeamento Pipedrive ────────────────────────────────────────
    if not pipedrive_complete:
        remaining = [t for t in [
            "pipedrive_get_persons", "pipedrive_get_deals", "pipedrive_get_activities"
        ] if t not in tools_called]
        next_tool_line = f"\nPRÓXIMA FERRAMENTA: {remaining[0]}" if remaining else ""
        return (
            base
            + "\n\nFase: Mapeamento Pipedrive."
            + f" Faltam (nesta ordem): {' → '.join(remaining)}."
            + next_tool_line
            + "\nNÃO inicie WhatsApp/Email antes de concluir os 4 passos do Pipedrive."
        )

    # ── Fase 3 — Investigação de comunicação ─────────────────────────────────
    if not comms_complete:
        # Determina exatamente qual é a próxima ferramenta a chamar
        next_action = ""
        
        # REGRA DE ESGOTAMENTO (Priority First): Esgota WhatsApp + Email do contato prioritário
        # antes de passar para o próximo da fila.
        for c in optimized_contacts:
            is_priority = _is_referred(c, goal_contacts) or _is_referred(c, referred_contacts) or c in active_contacts
            if is_priority:
                if not _searched(c, whatsapp_searched):
                    phone = contact_phones.get(c, "")
                    phone_hint = f" com contact='{c}' e phone='{phone}'" if phone else f" com contact='{c}'"
                    next_action = f"PRÓXIMA FERRAMENTA: whatsapp_get_messages{phone_hint}"
                    break
                if not _searched(c, email_searched):
                    next_action = f"PRÓXIMA FERRAMENTA: email_get_contact_history com contact_name='{c}'"
                    break
            
        if not next_action:
            # Se esgotou os prioritários ou não há, segue a ordem pendente normal
            if pending_wapp:
                c = pending_wapp[0]
                phone = contact_phones.get(c, "")
                phone_hint = f" com contact='{c}' e phone='{phone}'" if phone else f" com contact='{c}'"
                next_action = f"PRÓXIMA FERRAMENTA: whatsapp_get_messages{phone_hint}"
            elif pending_email:
                next_action = f"PRÓXIMA FERRAMENTA: email_get_contact_history com contact_name='{pending_email[0]}'"
            elif not org_wapp_done and org_name:
                next_action = f"PRÓXIMA FERRAMENTA: whatsapp_get_messages com contact='{org_name}'"
            elif not org_email_done and org_name:
                next_action = f"PRÓXIMA FERRAMENTA: email_get_contact_history com org_name='{org_name}'"
            else:
                next_action = "PRÓXIMA FERRAMENTA: whatsapp_get_messages ou email_get_contact_history para contatos restantes"

        # Lista completa de pendências para contexto
        pending_parts = []
        if pending_wapp:
            wa_list = []
            for c in pending_wapp:
                p = contact_phones.get(c)
                wa_list.append(f"{c} (tel: {p})" if p else c)
            pending_parts.append(f"WhatsApp de: {', '.join(wa_list)}")
        if pending_email:
            pending_parts.append(f"Email de: {', '.join(pending_email)}")
        if not org_wapp_done and org_name:
            pending_parts.append(f"WhatsApp pela empresa '{org_name}'")
        if not org_email_done and org_name:
            pending_parts.append(f"Email pela empresa '{org_name}'")
        pending_str = "; ".join(pending_parts) if pending_parts else "verificar contatos da organização"

        return (
            base
            + f"\n\nFase: Investigação de comunicação."
            + f"\nPendente: {pending_str}."
            + f"\n{next_action}."
            + "\n\nREGRA DE OURO (MUITO CRÍTICO): Se houver uma atividade pendente vinculada a uma pessoa específica (ex: Matheus Muniz), você DEVE começar a investigação OBRIGATORIAMENTE por essa pessoa. Não mude a ordem da fila."
            + "\n\nPROIBIDO: não chame pipedrive_get_all_activities (busca TODAS as empresas)."
            + " PROIBIDO: não use ferramentas de escrita (email_send, whatsapp_send_message) antes de completar a investigação."
            + " PROIBIDO: não use web_search_external durante investigação de empresa, EXCETO como último recurso para descobrir o domínio do site/e-mail caso não encontre contatos."
            + "\nPROIBIDO: NUNCA passe nomes de negócios (Deals) ou emojis nos campos de contato. Use APENAS o nome exato da empresa ou da pessoa."
            + "\n\nPRIORIDADE: examine as atividades para decidir a ordem. Se uma tarefa menciona 'fale com X' ou 'aguardando Y': essa pessoa vem antes."
            + "\nFOCO EXCLUSIVO NO CONTATO ATIVO (REGRA DE OURO): Se você identificar que as comunicações ativas da empresa estão sendo centralizadas em um interlocutor específico (ex: Gabriel, com mais de 10 mensagens no WhatsApp ou e-mails maduros), você deve focar EXCLUSIVAMENTE nele. NÃO gaste tokens nem tempo de execução buscando ou investigando contatos inativos/periféricos (como Gustavo, WOLDASCH, Wagner etc.), exceto se o contato ativo o recomendou explicitamente. Se o contato ativo já resolve o histórico, encerre as buscas adicionais e chame 'generate_dossier' imediatamente."
            + "\nRADAR: ao ler conversas, se aparecer nome novo, investigue também — mesmo fora do Pipedrive."
            + "\nCROSS-VALIDAÇÃO: compare Pipedrive com comunicações — aponte discrepâncias de datas, status ou pessoas não cadastradas."
        )

    # ── Fase 3b — Aguardando generate_dossier ────────────────────────────────
    if not dossier_done:
        return (
            base
            + "\n\nTodas as fontes foram investigadas. Chame generate_dossier agora."
        )

    # ── Fase 4 — Dossiê final ─────────────────────────────────────────────────
    return (
        base
        + "\n\nFase final. A investigação terminou. Escreva APENAS o Dossiê Final em texto corrido "
        "(parágrafos, sem bullets, sem emojis), contendo:"
        "\n1. Resumo do negócio: o que diz o Pipedrive (deal, valor, funil)."
        "\n2. Histórico de comunicação: o que foi falado exatamente (assuntos, nomes, datas, quem disse o quê)."
        "\n3. Situação real: status atual cruzando CRM com comunicações."
        "\n\nREGRAS:"
        "\n- NÃO escreva 'Ações Sugeridas:', 'Próximos Passos:' ou qualquer lista de ações — isso vem em seguida automaticamente."
        "\n- NÃO chame nenhuma ferramenta agora. Apenas escreva o dossiê."
        "\n- Finalize no ponto 3."
    )


def _suggest_actions_done(messages: list) -> bool:
    """Retorna True se suggest_next_actions já foi chamado em alguma mensagem do histórico."""
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            for block in content:
                if block.get("type") == "tool_use" and block.get("name") == "suggest_next_actions":
                    return True
    return False


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
            f"  1. pipedrive_get_persons → identificar contato com canal (WhatsApp ou e-mail)\n"
            f"  2. whatsapp_get_messages / email_get_contact_history → contexto das comunicações anteriores\n"
            f"  3. generate_sales_message(goal='cobrar retorno da proposta/cotação') → rascunho estratégico\n"
            f"  4. whatsapp_send_message / email_send → apresente ao João ANTES de enviar\n"
            f"  5. pipedrive_update_task(activity_id={act_id}, done=true) → marcar concluído após aprovação\n"
            f"⛔ PROIBIDO: NÃO crie nova tarefa — use pipedrive_update_task na atividade {act_id}.\n\n"
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


async def _agent_loop(
    messages: list,
    tools: list,
    start_iteration: int = 0,
    org_id: int | None = None,
    preferred: str | None = None,
    strict_mode: bool = False,
    process_id: str | None = None,
    direct_action: bool = False,
    parent_message_id: str | None = None,
    action_index: int | None = None,
    query_type: str = "agent_workflow",
) -> AsyncGenerator[str, None]:
    """Loop central do agente. Yields eventos NDJSON."""
    import re as _re
    process_id = process_id or f"proc_{uuid.uuid4().hex[:8]}"

    # Acumula resultados de ferramentas para degradação graciosa
    _collected_tool_summaries: list[str] = []
    # Garante que o evento final seja emitido apenas uma vez (dossiê)
    _final_emitted = False
    # Detecta se é uma tarefa multi-etapa (card de atividade do Pipedrive)
    # vs. aprovação de ação única — marcador injetado por _build_task_action_prompt
    _first_msg_content = messages[0].get("content", "") if messages else ""

    # Sinais que identificam um prompt de execução de tarefa CRM — gerado por
    # _build_task_action_prompt OU enviado manualmente via chat com o prefixo padrão.
    _TASK_SIGNALS = [
        "ATIVIDADE #",
        "Execute agora, começando pelo raciocínio",
        "EXECUTE ESTAS ETAPAS EM ORDEM",
        "ETAPA 1 — Pipedrive",
        "ETAPA 1 — ",
        "Investigue a empresa",
        "Execute a seguinte atividade do CRM",  # prefixo manual do frontend
    ]
    _has_task_signal = any(s in _first_msg_content for s in _TASK_SIGNALS)

    # Se o prompt parece uma tarefa CRM mas direct_action não foi sinalizado pelo
    # frontend (ex: enviado via chat normal), força o modo de tarefa automaticamente.
    if _has_task_signal and not direct_action:
        direct_action = True

    _is_task_action = direct_action and _has_task_signal
    _max_iters = (16 if _is_task_action else 6) if direct_action else MAX_ITERATIONS

    # Ferramentas cujos resultados nunca devem ser descartados do histórico:
    # sem eles o modelo perde a lista de contatos e começa a repetir ou pular buscas.
    _PINNED_TOOLS = {
        "pipedrive_get_org", "pipedrive_get_persons", "pipedrive_get_deals", "pipedrive_get_activities",
        "whatsapp_get_messages", "email_get_contact_history"
    }

    def _is_pinned(msg: dict) -> bool:
        content = msg.get("content", "")
        if isinstance(content, str):
            content_trimmed = content.strip()
            if content_trimmed.startswith("[") or content_trimmed.startswith("{"):
                try:
                    import json as _json
                    content = _json.loads(content_trimmed)
                except Exception:
                    try:
                        import ast as _ast
                        content = _ast.literal_eval(content_trimmed)
                    except Exception:
                        pass
        if not isinstance(content, list):
            return False
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "tool_use" and item.get("name") in _PINNED_TOOLS:
                return True
            if item.get("tool_name") in _PINNED_TOOLS:
                return True
        return False

    # Guard de deduplicação de tool calls — evita loop infinito quando modelo ignora anti-repetição
    _tool_call_history: set[tuple] = set()
    # Nome do contato dono da tarefa (person_name da atividade pendente do Pipedrive).
    # Capturado quando pipedrive_get_activities executa, antes da sanitização.
    _session_task_person: str | None = None

    for iteration in range(start_iteration, _max_iters):
        # Sai assim que suggest_next_actions foi chamado — cards já estão na UI,
        # não há razão para continuar investigando.
        if _suggest_actions_done(messages):
            return

        # Controle de ritmo (pacing sleep) defensivo para evitar estouro de RPM/TPM no Cerebras/Groq
        if iteration > 0:
            import asyncio as _asyncio
            from core.config import settings as _s
            _is_rate_sensitive = False
            if preferred:
                pref_lower = preferred.lower()
                if "cerebras" in pref_lower or "groq" in pref_lower:
                    _is_rate_sensitive = True
                elif pref_lower in (_s.ai_cerebras_models_list or []) or pref_lower in (_s.ai_groq_models_list or []):
                    _is_rate_sensitive = True
            
            if _is_rate_sensitive:
                pacing_delay = 1.5 if strict_mode else 1.0
                log.info("agent.llm.pacing_delay", provider=preferred, seconds=pacing_delay, iteration=iteration)
                await _asyncio.sleep(pacing_delay)

        # Corte de memória inteligente: preserva resultados críticos (lista de contatos,
        # deals e atividades) independente da posição no histórico, para que o modelo
        # não perca o mapa de quem investigar nas iterações finais do fluxo sequencial.
        if len(messages) > 40:
            pinned = [m for m in messages[1:-20] if _is_pinned(m)]
            recent = messages[-20:]
            pinned_set = set(id(m) for m in pinned)
            messages = [messages[0]] + pinned + [m for m in recent if id(m) not in pinned_set]

        # System prompt por fase: contém todas as instruções necessárias para o
        # momento atual — sem enviar o que já não é relevante.
        if direct_action and _is_task_action:
            # Seleciona prompt baseado na capacidade do modelo ativo
            # Modelos grandes (size >= 3): prompt de raciocínio autônomo
            # Modelos menores (size <= 2): instruções explícitas passo a passo
            try:
                from core.llm.router import get_model_size
                _model_size = get_model_size(preferred or "")
            except Exception:
                _model_size = 2
            # size >= 2 (flash, 32B, 17B+) → prompt autônomo; size 1 (8B, lite) → instruções explícitas
            system = SYSTEM_PROMPT_TASK_AGENT if _model_size >= 2 else SYSTEM_PROMPT_TASK_AGENT_BASIC
        elif direct_action:
            system = SYSTEM_PROMPT_DIRECT
        else:
            try:
                system = _build_phase_status(messages, query_type=query_type, org_id=org_id)
            except Exception:
                system = SYSTEM_PROMPT_POWERFUL

        # ── Tool calling ──────────────────────────────────────────────────────
        try:
            import asyncio as _asyncio
            _raw_log(process_id, "llm_request", {"system": system, "messages": messages, "iteration": iteration})
            _pending_events: list = []
            # Roda _call_with_tools como task em background para poder emitir
            # eventos (rate_wait, model_active) em tempo real enquanto ele aguarda.
            # Para tarefas CRM: força chamada de ferramenta enquanto Pipedrive core incompleto,
            # restringindo ao próximo tool core pendente para garantir a ordem correta.
            _force = False
            _allowed_core: list | None = None
            if _is_task_action:
                _CORE = {"pipedrive_get_org","pipedrive_get_persons","pipedrive_get_deals","pipedrive_get_activities"}
                _CORE_ORDER = ["pipedrive_get_org","pipedrive_get_persons","pipedrive_get_deals","pipedrive_get_activities"]
                _done: set[str] = set()
                for _m in messages:
                    _mc = _m.get("content","")
                    if isinstance(_mc, list):
                        for _b in _mc:
                            if isinstance(_b, dict):
                                _tn = _b.get("tool_name") or _b.get("name","")
                                if _b.get("type") in ("tool_result","tool_use") and _tn in _CORE:
                                    _done.add(_tn)
                _missing_core = _CORE - _done
                if _missing_core:
                    _force = True
                    # Restringe ao próximo tool core em ordem — impede Gemini de pular para
                    # whatsapp/email antes de terminar o Bloco 1 (Pipedrive).
                    _next_core = next((t for t in _CORE_ORDER if t not in _done), None)
                    if _next_core:
                        _allowed_core = [_next_core]

            # Detector de loop: se whatsapp_get_messages ou email_get_contact_history
            # foram chamados 3+ vezes, injeta instrução para o modelo avançar para ação.
            if _is_task_action and not _force:
                _comm_counts: dict[str, int] = {}
                for _m in messages:
                    _mc = _m.get("content","")
                    if isinstance(_mc, list):
                        for _b in _mc:
                            if isinstance(_b, dict) and _b.get("type") == "tool_use":
                                _tn = _b.get("name","")
                                if _tn in ("whatsapp_get_messages","email_get_contact_history","pipedrive_get_persons"):
                                    _comm_counts[_tn] = _comm_counts.get(_tn, 0) + 1
                _loop_detected = any(v >= 3 for v in _comm_counts.values())
                if _loop_detected and iteration < _max_iters - 2:
                    _contacts_summary = ""
                    for _m in messages:
                        _mc = _m.get("content","")
                        if isinstance(_mc, list):
                            for _b in _mc:
                                if isinstance(_b, dict) and _b.get("type") == "tool_result" and _b.get("tool_name") == "pipedrive_get_persons":
                                    _contacts_summary = str(_b.get("content",""))[:400]
                    messages.append({
                        "role": "user",
                        "content": (
                            "Você está em loop buscando histórico de comunicação. "
                            "Já investigou todos os canais disponíveis e não encontrou histórico. "
                            "PARE de buscar. Contatos da empresa: " + (_contacts_summary or "ver histórico anterior") + "\n"
                            "Próxima ação obrigatória: com base no que foi coletado, decida a ação "
                            "de comunicação adequada (email de reativação, WhatsApp, etc.) e execute. "
                            "Não busque mais histórico — não existe."
                        ),
                    })

            _llm_task = _asyncio.create_task(_call_with_tools(
                system, messages, tools,
                preferred=preferred, strict_mode=strict_mode,
                pending_events=_pending_events,
                force_tool_call=_force,
                allowed_tool_names=_allowed_core,
            ))
            while not _llm_task.done():
                while _pending_events:
                    yield _emit(_pending_events.pop(0))
                await _asyncio.sleep(0.05)
            response = await _llm_task  # propaga exceção se houver

            # Se deu certo, atualiza o preferred de forma "sticky" para manter o modelo que funcionou!
            if response and not strict_mode:
                succ_model = response.get("_successful_model")
                if succ_model:
                    preferred = succ_model
                    log.info("agent.llm.preferred.updated", preferred_model=preferred, iteration=iteration)

            # Esvazia quaisquer eventos restantes após conclusão
            for _ev in _pending_events:
                yield _emit(_ev)
            _pending_events.clear()
            _raw_log(process_id, "llm_response", {"response": response})
        except Exception as e:
            if _collected_tool_summaries:
                partial = "\n".join(f"• {s}" for s in _collected_tool_summaries)
                yield _emit({
                    "type": "final",
                    "response": (
                        f"⚠️ Os serviços de IA estão temporariamente sobrecarregados. "
                        f"Aqui estão os dados coletados até agora:\n\n{partial}\n\n"
                        f"Tente novamente em alguns minutos para a análise completa."
                    ),
                })
            else:
                _raw_log(process_id, "agent_error", {"content": f"Erro ao chamar LLM: {e}"})
                yield _emit({"type": "error", "content": f"Erro ao chamar LLM: {e}"})
            return

        content = response.get("content", [])
        stop_reason = response.get("stop_reason", "end_turn")

        text_blocks = [b for b in content if b.get("type") == "text"]
        tool_use_blocks = [b for b in content if b.get("type") == "tool_use"]

        # ── Fallback: alguns modelos menores (Cerebras/Groq 8B) retornam tool calls
        # como texto JSON — seja como resposta exclusiva (sem tool_use_blocks) ou
        # embutido no texto junto com um tool call estruturado real (resposta dupla).
        # Em ambos os casos: detecta, converte e limpa o JSON do texto da UI.
        if text_blocks:
            def _extract_json_objects(text: str) -> list[str]:
                """Extrai objetos JSON balanceados (suporta aninhamento)."""
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

            _combined_text = " ".join(b.get("text", "") for b in text_blocks)
            for _jc in _extract_json_objects(_combined_text):
                try:
                    _obj = json.loads(_jc)
                    _tool_name = _obj.get("name") or _obj.get("function")
                    _tool_args = _obj.get("arguments") or _obj.get("input") or _obj.get("parameters") or {}
                    if isinstance(_tool_args, str):
                        try:
                            _tool_args = json.loads(_tool_args)
                        except Exception:
                            _tool_args = {}
                    if _tool_name and _tool_name in TOOLS and isinstance(_tool_args, dict):
                        # Sem tool_use estruturado: converte o JSON em tool_use real
                        if not tool_use_blocks:
                            tool_use_blocks.append({
                                "type": "tool_use",
                                "id": f"tc_fallback_{uuid.uuid4().hex[:8]}",
                                "name": _tool_name,
                                "input": _tool_args,
                            })
                            stop_reason = "tool_use"
                        # Com ou sem tool_use: remove o JSON do texto para não poluir a UI
                        text_blocks = [
                            {**b, "text": b.get("text", "").replace(_jc, "").strip()}
                            for b in text_blocks
                        ]
                        text_blocks = [b for b in text_blocks if b.get("text")]
                        # Reconstrói content para que o histórico reflita o tool_use real.
                        # Sem isso, _build_phase_status não rastreia whatsapp_searched/email_searched
                        # a partir dos args do assistente — a fase fica em loop infinito.
                        content = text_blocks + tool_use_blocks
                        break
                except Exception:
                    pass

        # ── Thinking: gerado DEPOIS de saber qual ferramenta será chamada ────
        # Prioridade: texto nativo completo > auxiliar completo > nada (sem fallback seco).
        # O label da ferramenta já é mostrado pelo tool_call event — não duplicar.
        if tool_use_blocks:
            first_tool = tool_use_blocks[0]
            native_text = " ".join(b.get("text", "").strip() for b in text_blocks).strip()
            native_is_complete = bool(native_text and native_text[-1] in ".!?")

            if native_is_complete and len(native_text) > 40:
                # Modelo principal (Claude/Gemini) gerou raciocínio genuíno
                yield _emit({"type": "thinking", "content": native_text})
            else:
                # Modelo não narrou (Groq) — tenta auxiliar de qualidade
                # skip_groq=True evita dobrar quota quando main também é Groq,
                # mas agora sem injection o risco de comportamento errado é zero,
                # então só skipamos quando há alternativa disponível.
                from core.config import settings as _s
                _groq_models = set(_s.ai_groq_models_list or [])
                _cerebras_models = set(_s.ai_cerebras_models_list or [])
                
                _main_is_groq = (
                    not preferred
                    or (preferred or "").lower() == "groq"
                    or preferred in _groq_models
                )
                _main_is_cerebras = (
                    (preferred or "").lower() == "cerebras"
                    or preferred in _cerebras_models
                )
                
                # Só pula Groq se Gemini ou Cerebras estiverem disponíveis
                _has_alt_for_groq = bool(
                    (_s.GEMINI_API_KEY and _s.ai_gemini_models_list)
                    or (_s.CEREBRAS_API_KEY and _s.ai_cerebras_models_list)
                )
                # Só pula Cerebras se Gemini ou Groq estiverem disponíveis
                _has_alt_for_cerebras = bool(
                    (_s.GEMINI_API_KEY and _s.ai_gemini_models_list)
                    or (_s.GROQ_API_KEY and _s.ai_groq_models_list)
                )
                
                _tn = first_tool.get("name", "")
                _ta = first_tool.get("input") or {}

                # Template para todas as ferramentas — evita chamada LLM extra (5-15s por tool).
                # O modelo principal já gera texto quando tem contexto real; aqui só cobrimos
                # o caso em que ele chamou a ferramenta sem texto (ex: Gemini com mode=ANY).
                if _tn != "suggest_next_actions":
                    yield _emit({"type": "thinking", "content": _get_thinking_fallback(_tn, _ta)})

        # Resposta final (sem tool calls)
        if stop_reason == "end_turn" or not tool_use_blocks:
            response_text = " ".join(b.get("text", "") for b in text_blocks).strip()
            if not response_text:
                response_text = "Tarefa concluída."

            # Modo execução direta: verificar se a Fase 1 foi concluída antes de encerrar
            if direct_action and _is_task_action:
                _CTX_TOOLS = {
                    "pipedrive_get_org", "pipedrive_get_persons", "pipedrive_get_deals",
                    "pipedrive_get_activities", "whatsapp_get_messages", "email_get_contact_history",
                }
                # Detecta quais ferramentas de contexto já foram chamadas no histórico
                _called_ctx: set[str] = set()
                for _m in messages + [{"role": "assistant", "content": content}]:
                    _mc = _m.get("content", "")
                    if isinstance(_mc, list):
                        for _b in _mc:
                            if isinstance(_b, dict):
                                if _b.get("type") == "tool_use" and _b.get("name") in _CTX_TOOLS:
                                    _called_ctx.add(_b["name"])
                                elif _b.get("type") == "tool_result" and _b.get("tool_name") in _CTX_TOOLS:
                                    _called_ctx.add(_b["tool_name"])

                _missing_ctx = _CTX_TOOLS - _called_ctx
                # Só bloqueia se faltam ferramentas core (org, persons, deals, activities)
                # — as de comunicação podem ser omitidas pelo padrão "Encontrar Decisor"
                _CORE_CTX = {"pipedrive_get_org", "pipedrive_get_persons", "pipedrive_get_deals", "pipedrive_get_activities"}
                _missing_core = _CORE_CTX - _called_ctx

                # Ordem preferida de execução da fase 1
                _CTX_ORDER = [
                    "pipedrive_get_org", "pipedrive_get_persons",
                    "pipedrive_get_deals", "pipedrive_get_activities",
                    "whatsapp_get_messages", "email_get_contact_history",
                ]
                _next_tool = next((t for t in _CTX_ORDER if t not in _called_ctx), None)

                if _missing_core and _next_tool and iteration < _max_iters - 2:
                    # Fase 1 incompleta — injeta continuação com a ferramenta EXATA a chamar
                    messages.append({"role": "assistant", "content": content})
                    messages.append({
                        "role": "user",
                        "content": (
                            f"A investigação não foi concluída. "
                            f"CHAME AGORA: {_next_tool}\n"
                            f"Ferramentas ainda pendentes: {', '.join(t for t in _CTX_ORDER if t not in _called_ctx)}\n"
                            f"Execute {_next_tool} imediatamente. Não gere texto — apenas chame a ferramenta."
                        ),
                    })
                    continue

                # ── Interceptor: contatos com canal ainda não investigados ─────────────
                # Para tarefas de follow-up/comunicação, garante que TODOS os contatos
                # ── Interceptor: Email obrigatório para contato-tarefa ──────────────────────
                # Para tarefas com contato específico (_session_task_person), sempre busca
                # TAMBÉM o email após WhatsApp — independente do resultado do WhatsApp.
                if _session_task_person and _is_task_action and iteration < _max_iters - 2:
                    _tpn_first = _session_task_person.split()[0].lower()
                    _task_wa_done = False
                    _task_email_done = False
                    for _hm in messages + [{"role": "assistant", "content": content}]:
                        _hc = _hm.get("content", "")
                        if not isinstance(_hc, list): continue
                        for _hb in _hc:
                            if not isinstance(_hb, dict) or _hb.get("type") != "tool_use": continue
                            _inp = _hb.get("input") or {}
                            if _hb.get("name") == "whatsapp_get_messages":
                                if _tpn_first in (_inp.get("contact") or "").lower():
                                    _task_wa_done = True
                            elif _hb.get("name") == "email_get_contact_history":
                                if (_tpn_first in (_inp.get("contact_name") or "").lower()
                                        or _tpn_first in (_inp.get("org_name") or "").lower()):
                                    _task_email_done = True
                    if _task_wa_done and not _task_email_done:
                        messages.append({"role": "assistant", "content": content})
                        messages.append({
                            "role": "user",
                            "content": (
                                f"Você já verificou o WhatsApp de {_session_task_person}. "
                                f"OBRIGATÓRIO: verifique também o e-mail antes de finalizar — "
                                f"chame email_get_contact_history com contact_name='{_session_task_person}' "
                                f"para ter o histórico completo de comunicações."
                            ),
                        })
                        continue

                # com canal registrado (WhatsApp ou telefone/email) sejam buscados antes
                # de o agente finalizar. Impede que o modelo conclua "sem histórico" depois
                # de buscar apenas o contato principal.
                if iteration < _max_iters - 2:
                    # Extrai contatos com canal do resultado de pipedrive_get_persons.
                    # O conteúdo armazenado é texto sanitizado, não JSON estruturado.
                    # Formato: "• [ID:61] Lucas (11 4591-1807)" — "sem contato" = sem canal.
                    _persons_with_channel: list[str] = []
                    import json as _json2
                    import re as _re_pc
                    # Usa apenas o resultado MAIS RECENTE de pipedrive_get_persons
                    # para evitar contaminação de sessões/chats anteriores no histórico.
                    _last_persons_msg = None
                    for _m in messages:
                        _mc = _m.get("content", "")
                        if not isinstance(_mc, list): continue
                        for _b in _mc:
                            if isinstance(_b, dict) and _b.get("type") == "tool_result" and _b.get("tool_name") == "pipedrive_get_persons":
                                _last_persons_msg = _b
                    for _m in ([{"content": [_last_persons_msg]}] if _last_persons_msg else []):
                        _mc = _m.get("content", "")
                        if not isinstance(_mc, list): continue
                        for _b in _mc:
                            if not isinstance(_b, dict): continue
                            if _b.get("type") != "tool_result" or _b.get("tool_name") != "pipedrive_get_persons": continue
                            _raw_c = _b.get("content", "")
                            # Desserializa o JSON externo (que encapsula a string sanitizada)
                            try:
                                _text = _json2.loads(_raw_c) if isinstance(_raw_c, str) else _raw_c
                            except Exception:
                                _text = _raw_c
                            # Caso dict com "persons" (raro — resultado não sanitizado)
                            if isinstance(_text, dict):
                                for _p in (_text.get("persons") or []):
                                    _pn = _p.get("name", "")
                                    if _pn and (_p.get("phone") or _p.get("email")):
                                        _persons_with_channel.append(_pn)
                            elif isinstance(_text, str):
                                # Formato: "• [ID:NNN] Nome (telefone_ou_email)"
                                # Pula linhas com "sem contato" — são contatos sem canal
                                for _m2 in _re_pc.finditer(
                                    r'•\s*\[ID:\d+\]\s*([^(\n]+?)\s*\(([^)]+)\)',
                                    _text
                                ):
                                    _pname_raw = _m2.group(1).strip()
                                    _pcontact  = _m2.group(2).strip()
                                    if _pname_raw and _pcontact and _pcontact != "sem contato":
                                        _persons_with_channel.append((_pname_raw, _pcontact))

                    # Prioriza o contato dono da tarefa — usa _session_task_person capturado
                    # durante a execução de pipedrive_get_activities (dado raw, antes da sanitização).
                    if _session_task_person and _persons_with_channel:
                        _tpn_lower = _session_task_person.lower()
                        _task_entry = next(
                            (p for p in _persons_with_channel
                             if _tpn_lower in p[0].lower() or p[0].lower().split()[0] in _tpn_lower),
                            None
                        )
                        if _task_entry and _persons_with_channel.index(_task_entry) != 0:
                            _persons_with_channel.remove(_task_entry)
                            _persons_with_channel.insert(0, _task_entry)

                    # Descobre quais contatos já foram buscados via whatsapp ou email
                    _already_searched: set[str] = set()
                    for _m in messages + [{"role": "assistant", "content": content}]:
                        _mc = _m.get("content", "")
                        if not isinstance(_mc, list): continue
                        for _b in _mc:
                            if not isinstance(_b, dict): continue
                            if _b.get("type") != "tool_use": continue
                            _tn2 = _b.get("name", "")
                            _ta2 = _b.get("input") or {}
                            if _tn2 == "whatsapp_get_messages":
                                _already_searched.add((_ta2.get("contact") or "").lower())
                            elif _tn2 == "email_get_contact_history":
                                _cn = (_ta2.get("contact_name") or _ta2.get("org_name") or "").lower()
                                if _cn: _already_searched.add(_cn)

                    # Nome da organização para busca por empresa
                    _org_name_for_search = ""
                    for _m in messages:
                        _mc = _m.get("content", "")
                        if not isinstance(_mc, list): continue
                        for _b in _mc:
                            if not isinstance(_b, dict): continue
                            if _b.get("type") == "tool_result" and _b.get("tool_name") == "pipedrive_get_org":
                                try:
                                    _od = _json2.loads(_b.get("content", "{}"))
                                    _org_name_for_search = (_od.get("org") or {}).get("name") or _od.get("name") or ""
                                except Exception:
                                    pass

                    # Encontra o próximo contato com canal ainda não buscado
                    _next_unsearched = None
                    for _pname, _pcontact in _persons_with_channel:
                        if _pname.lower() not in _already_searched and _pname.split()[0].lower() not in _already_searched:
                            _next_unsearched = (_pname, _pcontact)
                            break

                    _ai_response_text = " ".join(b.get("text", "") for b in text_blocks).lower()
                    
                    # Detecta se já gerou rascunho de mensagem (significa que já identificou o decisor e o histórico)
                    _has_draft = False
                    for _m in messages + [{"role": "assistant", "content": content}]:
                        _mc = _m.get("content", "")
                        if isinstance(_mc, list):
                            for _b in _mc:
                                if isinstance(_b, dict) and (_b.get("tool_name") == "generate_sales_message" or (_b.get("type") == "tool_use" and _b.get("name") == "generate_sales_message")):
                                    _has_draft = True
                                    break
                        if _has_draft: break

                    _found_decision_maker = _has_draft or ("decisor" in _ai_response_text and any(word in _ai_response_text for word in ["encontrado", "confirmado", "identificado"]))

                    # Se já achou decisor ou gerou rascunho, ignora esgotamento forçado.
                    # Para tarefas diretas (_is_task_action), somos mais flexíveis apenas se JÁ encontrou
                    # histórico útil. Se WhatsApp estava desconectado, ainda força busca de email.
                    _has_useful_history = any(
                        True
                        for _hm in messages + [{"role": "assistant", "content": content}]
                        for _hb in (_hm.get("content") if isinstance(_hm.get("content"), list) else [])
                        if isinstance(_hb, dict)
                        and _hb.get("type") == "tool_result"
                        and _hb.get("tool_name") in ("whatsapp_get_messages", "email_get_contact_history")
                        and "desconectado" not in str(_hb.get("content", "")).lower()
                        and "inacess" not in str(_hb.get("content", "")).lower()
                        and "não encontrado" not in str(_hb.get("content", "")).lower()
                    )
                    if _next_unsearched and _persons_with_channel and not _found_decision_maker:
                        if _is_task_action and _already_searched and _has_useful_history:
                            # Já encontrou histórico útil — não força busca adicional
                            pass
                        else:
                            _first_name = _next_unsearched[0].split()[0]
                            _phone_val = _next_unsearched[1]
                            _unsearched_list = [p[0] for p in _persons_with_channel
                                                if p[0].lower() not in _already_searched
                                                and p[0].split()[0].lower() not in _already_searched]
                            _phone_param = f", phone='{_phone_val}'" if "@" not in _phone_val else ""

                            # Se WhatsApp estiver desconectado ou com falha, força email em vez de outra tentativa
                            _wa_disconnected_now = any(
                                "desconectado" in str(_hb.get("content", "")).lower() or
                                "inacess" in str(_hb.get("content", "")).lower() or
                                "http 5" in str(_hb.get("content", "")).lower() or
                                "sem lid" in str(_hb.get("content", "")).lower() or
                                "sem conversa ativa" in str(_hb.get("content", "")).lower()
                                for _hm in messages + [{"role": "assistant", "content": content}]
                                for _hb in (_hm.get("content") if isinstance(_hm.get("content"), list) else [])
                                if isinstance(_hb, dict) and _hb.get("type") == "tool_result"
                                and _hb.get("tool_name") == "whatsapp_get_messages"
                            )
                            if _wa_disconnected_now:
                                _next_for_email = _next_unsearched[0]
                                _org_label = _org_name_for_search or "a empresa"
                                messages.append({"role": "assistant", "content": content})
                                messages.append({
                                    "role": "user",
                                    "content": (
                                        f"WhatsApp está desconectado. OBRIGATÓRIO: busque o histórico de e-mail como alternativa.\n"
                                        f"Chame email_get_contact_history com contact_name='{_next_for_email}', org_name='{_org_label}' agora.\n"
                                        f"Só conclua 'sem histórico' após verificar e-mail também."
                                    ),
                                })
                            else:
                                messages.append({"role": "assistant", "content": content})
                                messages.append({
                                    "role": "user",
                                    "content": (
                                        f"ATENÇÃO: Você não esgotou todos os contatos com canal antes de finalizar.\n"
                                        f"Contatos com canal registrado ainda não buscados: {', '.join(_unsearched_list)}\n"
                                        f"OBRIGATÓRIO: busque agora whatsapp_get_messages com contact='{_first_name}'{_phone_param} "
                                        f"antes de redigir qualquer mensagem. "
                                        f"Só conclua 'sem histórico' após verificar TODOS os contatos com canal."
                                    ),
                                })
                            continue

                    # ── Interceptor: sem canal → forçar open_hierarchy_drawer (anti-alucinação) ──
                    # O LLM tende a escrever "abri o mapeador" em texto em vez de chamar a tool.
                    # Condição: investigação concluída + zero contatos com canal + tarefa é encontrar decisor.
                    _is_find_decisor_task = any(kw in _first_msg_content.lower() for kw in [
                        "encontrar contato", "encontrar decisor", "open_hierarchy_drawer",
                        "encontrar o contato", "identificar contato", "localizar contato",
                    ])
                    _hierarchy_already_called = any(
                        isinstance(_b, dict) and (
                            (_b.get("type") == "tool_use" and _b.get("name") == "open_hierarchy_drawer") or
                            (_b.get("type") == "tool_result" and _b.get("tool_name") == "open_hierarchy_drawer")
                        )
                        for _m in messages + [{"role": "assistant", "content": content}]
                        for _b in (_m.get("content") if isinstance(_m.get("content"), list) else [])
                    )
                    if (
                        _is_find_decisor_task
                        and not _persons_with_channel
                        and not _missing_core
                        and not _hierarchy_already_called
                    ):
                        _org_hint = _org_name_for_search or ""
                        messages.append({"role": "assistant", "content": content})
                        messages.append({
                            "role": "user",
                            "content": (
                                f"AÇÃO OBRIGATÓRIA: Investigação concluída — nenhum contato com canal válido encontrado.\n"
                                f"NÃO descreva esta ação em texto — CHAME A FERRAMENTA DIRETAMENTE AGORA.\n"
                                f"Chame: open_hierarchy_drawer"
                                + (f" com org_name='{_org_hint}'" if _org_hint else "")
                                + f"\nProibido escrever 'abri o mapeador' sem chamar a tool."
                            ),
                        })
                        continue

                # ── Interceptor: Rascunho gerado mas NÃO enviado (REGRA DE OURO) ─────────────
                if _is_task_action and iteration < _max_iters - 2:
                    _has_draft_now = False
                    _has_sent_now = False
                    _SEND_TOOLS = {"whatsapp_send_message", "email_send", "email_reply", "pipedrive_update_task", "pipedrive_create_task"}
                    
                    for _m in messages + [{"role": "assistant", "content": content}]:
                        _mc = _m.get("content", "")
                        if isinstance(_mc, list):
                            for _b in _mc:
                                if not isinstance(_b, dict): continue
                                _tn_check = _b.get("tool_name") or _b.get("name")
                                if _tn_check == "generate_sales_message":
                                    _has_draft_now = True
                                elif _tn_check in _SEND_TOOLS:
                                    _has_sent_now = True
                    
                    if _has_draft_now and not _has_sent_now:
                        # Força o envio do rascunho
                        messages.append({"role": "assistant", "content": content})
                        messages.append({
                            "role": "user",
                            "content": (
                                "REGRA DE OURO: Você gerou um rascunho de mensagem mas não chamou a ferramenta de envio para aprovação.\n"
                                "O 'Sucesso' da sua tarefa é fazer o card de aprovação aparecer para o João Luccas.\n"
                                "CHAME AGORA: whatsapp_send_message (ou email_send) com o texto do rascunho.\n"
                                "É PROIBIDO terminar o turno apenas com texto quando há um rascunho pronto."
                            ),
                        })
                        continue

                    # ── Interceptor: Histórico encontrado mas rascunho NÃO gerado (OBRIGATÓRIO PARA FOLLOW-UP) ──
                    if not _has_draft_now and not _has_sent_now:
                        _is_followup = any(kw in _first_msg_content.lower() for kw in ["follow-up", "cobrar retorno", "acompanhar", "orçamento"])
                        if _is_followup:
                            _found_history = False
                            # Verifica tanto o histórico quanto os resultados do turno atual
                            all_recent_results = []
                            for _m in messages:
                                _mc = _m.get("content", "")
                                if isinstance(_mc, list):
                                    all_recent_results.extend([_b for _b in _mc if isinstance(_b, dict)])
                            all_recent_results.extend([_b for _b in tool_results if isinstance(_b, dict)])

                            for _b in all_recent_results:
                                if _b.get("type") == "tool_result" and _b.get("tool_name") in ("whatsapp_get_messages", "email_get_contact_history"):
                                    _res_content = str(_b.get("content", "")).lower()
                                    if ("nenhuma mensagem" not in _res_content and 
                                        "0 mensagens" not in _res_content and 
                                        "nenhum e-mail" not in _res_content and
                                        "0 e-mails" not in _res_content):
                                        _found_history = True
                                        break
                            
                            if _found_history:
                                messages.append({"role": "assistant", "content": content})
                                messages.append({
                                    "role": "user",
                                    "content": (
                                        "ATENÇÃO: Você encontrou histórico de comunicação relevante mas NÃO gerou o rascunho de follow-up.\n"
                                        "Para tarefas de follow-up/cobrar retorno, sua missão OBRIGATORIAMENTE deve terminar com um rascunho pronto para envio.\n"
                                        "CHAME AGORA: generate_sales_message para criar a mensagem agressiva/técnica baseada no histórico encontrado.\n"
                                        "É PROIBIDO finalizar a tarefa apenas relatando que encontrou as mensagens."
                                    ),
                                })
                                continue

            # Emite resultado final
            if direct_action:
                if not _final_emitted:
                    _raw_log(process_id, "agent_final_response", {"response": response_text})
                    yield _emit({"type": "final", "response": response_text})
                return

            # Interceptor anti-permissão: se o modelo pediu permissão em vez de agir,
            # injeta uma correção e força mais uma iteração de ferramentas.
            _PERMISSION_PHRASES = [
                "você gostaria", "gostaria de verificar", "gostaria de buscar",
                "deseja continuar", "deseja verificar", "posso verificar",
                "posso buscar", "posso investigar", "quer que eu",
                "para prosseguir", "preciso de mais informações",
                "você prefere", "prefere que eu",
            ]
            _resp_lower = response_text.lower()
            _is_asking_permission = any(p in _resp_lower for p in _PERMISSION_PHRASES)

            if _is_asking_permission and iteration < MAX_ITERATIONS - 2:
                messages.append({"role": "assistant", "content": content})
                
                try:
                    _status = _build_phase_status(messages, query_type=query_type, org_id=org_id)
                    m_action = _re.search(r'(PRÓXIMA FERRAMENTA:[^\n]+)', _status)
                    action_str = m_action.group(1) if m_action else "Consulte o plano de fases para decidir o próximo passo."
                except Exception:
                    _status = "Status desconhecido"
                    action_str = "Continue investigando ou chame a ferramenta final."

                messages.append({
                    "role": "user",
                    "content": (
                        "PROIBIDO pedir permissão. "
                        "Não faça perguntas de confirmação ao usuário durante a investigação.\n\n"
                        f"OBRIGATÓRIO AGORA: {action_str}\n\n"
                        f"Contexto atual:\n{_status}"
                    ),
                })
                continue

            # Extrai dados reais do histórico para sugestões e prompts
            found_org = ""
            found_deal_id = None
            found_activities = []
            found_contacts = []
            for _m in messages:
                _m_content = _m.get("content", "")
                if isinstance(_m_content, list):
                    for _item in _m_content:
                        if isinstance(_item, dict) and _item.get("type") == "tool_result":
                            _t_name = _item.get("tool_name", "")
                            _t_content = str(_item.get("content", ""))
                            try:
                                _t_data = json.loads(_t_content) if _t_content.strip().startswith(("{", "[")) else {}
                            except Exception:
                                _t_data = {}
                            if _t_name in ("pipedrive_get_org", "pipedrive_get_persons"):
                                if _t_name == "pipedrive_get_org":
                                    found_org = _t_data.get("org", {}).get("name") or _t_data.get("name") or found_org
                                _p_list = _t_data.get("persons") or []
                                for _p in _p_list:
                                    _p_name = _p.get("name")
                                    if _p_name:
                                        _p_name_clean = _p_name.strip().lower()
                                        if _p_name_clean not in [c.get("name", "").strip().lower() for c in found_contacts]:
                                            found_contacts.append(_p)
                            elif _t_name == "pipedrive_get_deals":
                                _d_list = _t_data.get("deals") or []
                                for _d in _d_list:
                                    if _d.get("status") == "open":
                                        found_deal_id = _d.get("id") or found_deal_id
                            elif _t_name == "pipedrive_get_activities":
                                _p_list = _t_data.get("pending") or []
                                for _a in _p_list:
                                    _act_id = _a.get("id")
                                    if _act_id and _act_id not in [act.get("id") for act in found_activities]:
                                        found_activities.append({
                                            "id": _act_id,
                                            "subject": _a.get("subject", "Sem assunto"),
                                            "due_date": _a.get("due_date", "sem data")
                                        })

            # Interceptor anti-finalização prematura e injeção de suggest_next_actions
            if iteration < MAX_ITERATIONS - 2:
                try:
                    _msgs_with_current = messages + [{"role": "assistant", "content": content}]
                    _status = _build_phase_status(_msgs_with_current, query_type=query_type, org_id=org_id)
                    # Para queries não-investigativas, o modo universal já controla a completude.
                    # Para investigações, detectamos pela fase no _status.
                    _is_non_investigation = query_type not in ("deal_status", "agent_workflow")
                    _is_complete = (
                        _is_non_investigation
                        or _is_task_action
                        or "Fase final" in _status
                        or "resposta final" in _status.lower()
                        or "responda à pergunta" in _status.lower()
                        or "apresente os" in _status.lower()
                        or "escreva a resposta final" in _status.lower()
                        or "não chame mais ferramentas" in _status.lower()
                    )

                    if not _is_complete and stop_reason == "end_turn" and not tool_use_blocks:
                        # Investigação incompleta — força continuar (só para respostas de texto puro)
                        m_action = _re.search(r'(PRÓXIMA FERRAMENTA:[^\n]+)', _status)
                        action_str = m_action.group(1) if m_action else "Consulte o plano de fases."
                        messages.append({"role": "assistant", "content": content})
                        messages.append({
                            "role": "user",
                            "content": (
                                f"ERRO: INVESTIGAÇÃO INCOMPLETA. Você tentou finalizar a resposta sem usar a ferramenta obrigatória.\n"
                                f"Para a investigação estar completa, você DEVE executar a próxima etapa.\n\n"
                                f"OBRIGATÓRIO AGORA:\n{action_str}\n\n"
                                f"Contexto:\n{_status}"
                            ),
                        })
                        continue

                    # Investigação completa — verifica se suggest_next_actions já foi chamado.
                    # Para tarefas diretas (_is_task_action), não sugerimos ações extras ao final.
                    if not _is_task_action and not _final_emitted and not _suggest_actions_done(_msgs_with_current) and stop_reason == "end_turn" and not tool_use_blocks:
                        # Emite o dossiê agora e força turno dedicado para suggest_next_actions
                        _raw_log(process_id, "agent_final_response", {"response": response_text})
                        yield _emit({"type": "final", "response": response_text})
                        _final_emitted = True

                        real_data_summary = []
                        if found_org:
                            real_data_summary.append(f"  - Organização/Empresa: '{found_org}'")
                        if found_deal_id:
                            real_data_summary.append(f"  - ID do Negócio Comercial (deal_id): {found_deal_id}")
                        if found_activities:
                            real_data_summary.append("  - Atividades Pendentes no Pipedrive (IDs REAIS):")
                            for _a in found_activities:
                                real_data_summary.append(f"    • ID: {_a['id']} | Assunto: '{_a['subject']}' | Vencimento: {_a['due_date']}")
                        if found_contacts:
                            real_data_summary.append("  - Contatos Atuais no Pipedrive:")
                            for _c in found_contacts:
                                real_data_summary.append(f"    • {_c.get('name')} (E-mail: {_c.get('email') or 'N/A'}, Tel: {_c.get('phone') or 'N/A'})")
                        else:
                            real_data_summary.append("  - Contatos Atuais no Pipedrive: Nenhum contato cadastrado ainda!")

                        real_data_str = "\n".join(real_data_summary) if real_data_summary else "  (Nenhum ID específico encontrado)"

                        messages.append({"role": "assistant", "content": content})
                        context_lines = [s for s in _collected_tool_summaries[-10:] if s]
                        context_str = "\n".join(f"  • {s}" for s in context_lines) if context_lines else "  (sem dados específicos)"
                        messages.append({
                            "role": "user",
                            "content": (
                                f"Dossiê entregue. DADOS REAIS EXTRAÍDOS DO HISTÓRICO (USE APENAS ESTES IDS):\n{real_data_str}\n\n"
                                f"RESUMO DAS FONTES:\n{context_str}\n\n"
                                "Você é um Consultor de Vendas B2B sênior e altamente estratégico. "
                                "Chame OBRIGATORIAMENTE 'suggest_next_actions' com 3-6 ações específicas, contextualizadas e comercialmente brilhantes.\n"
                                "Cada ação DEVE ter:\n"
                                "• 'label': texto curto, persuasivo e atraente para o botão (comercialmente focado)\n"
                                "• 'prompt': instrução autossuficiente com IDs e parâmetros REAIS obtidos nas buscas.\n\n"
                                "REGRAS OBRIGATÓRIAS DE RACIOCÍNIO COMERCIAL:\n"
                                "1. EVITAR CADASTROS DUPLICADOS (CRÍTICO): Se o nome da pessoa identificada na comunicação (ex: Gabriel) "
                                "já está listado nos 'Contatos Atuais no Pipedrive' fornecidos acima (mesmo com pequenas variações), "
                                "você está ABSOLUTAMENTE PROIBIDO de sugerir criar o contato. O usuário considera isso um erro grave. "
                                "Apenas sugira 'pipedrive_create_person' se for um contato 100% novo revelado no histórico que não esteja no CRM. "
                                "(Lembre-se: João Moura é o vendedor, nunca cadastre ele).\n"
                                "   Prompt caso novo: 'Execute pipedrive_create_person: name=[NOME_REAL_DO_CONTATO], email=[EMAIL_REAL], org_name=[NOME_DA_EMPRESA]' (substitua sempre as chaves por valores reais, nunca use palavras genéricas ou colchetes no prompt final)\n\n"
                                "2. CONCLUIR ATIVIDADE: Se há uma atividade pendente de follow-up e o histórico de e-mails ou WhatsApp "
                                "mostra que já houve uma interação/resposta real recente, sugira marcar essa atividade pendente como feita.\n"
                                "   O 'label' da ação DEVE conter obrigatoriamente o assunto da tarefa no formato: 'Concluir atividade pendente · [Assunto da Tarefa]'.\n"
                                "   Exemplo: se a tarefa pendente tem o assunto 'Ligar para Gabriel', o label deve ser exatamente: 'Concluir atividade pendente · Ligar para Gabriel'.\n"
                                "   Prompt: 'Execute pipedrive_update_task com activity_id=[ID_NUMERICO_REAL] e done=true' (substitua sempre pelo ID numérico real da atividade encontrado no CRM, nunca escreva a palavra literal 'ID')\n\n"
                                "3. ANÁLISE DE OBJEÇÃO DE PREÇO (MUITO IMPORTANTE): Verifique atentamente se o contato (ex: Gabriel) indicou "
                                "nas mensagens de WhatsApp ou E-mail que nosso preço/orçamento está alto, caro, fora do orçamento, ou que "
                                "está comparando com a concorrência que é mais barata. Neste cenário de objeção de preço:\n"
                                "   - NÃO sugira sequências genéricas de follow-ups persistentes pedindo reunião. Isso afasta o cliente e é ineficaz.\n"
                                "   - Em vez disso, crie um plano sob medida focado em contornar a objeção de preço, ajustando propostas, "
                                "estudando margens e negociando termos técnicos de valor. A sequência de 5 tarefas no Pipedrive deve ser:\n"
                                "     * Tarefa 1: Estudo interno de custos e viabilidade de desconto de margem (tipo='task', due_date='<HOJE+1d>')\n"
                                "     * Tarefa 2: WhatsApp/Email rápido de alinhamento com o contato, informando que estamos revisando os custos (tipo='task', due_date='<HOJE+1d>')\n"
                                "     * Tarefa 3: Elaborar e Enviar Proposta Comercial Revisada com a melhor margem possível ou especificações alternativas para caber no budget (tipo='task', due_date='<HOJE+3d>')\n"
                                "     * Tarefa 4: Ligação consultiva para entender as propostas dos concorrentes e termos técnicos (tipo='call', due_date='<HOJE+6d>')\n"
                                "     * Tarefa 5: Ligação/Reunião de fechamento comercial definitivo (tipo='call' ou 'meeting', due_date='<HOJE+10d>')\n"
                                "   - Se NÃO houver reclamação de preço alto no histórico: use uma sequência padrão de 5 follow-ups progressivos de qualificação "
                                "visando agendar uma reunião de apresentação.\n"
                                "   Exemplo de prompt para sequência de follow-ups adaptada:\n"
                                "   label: 'Criar plano de 5 tarefas de negociação de preço para <CONTATO>' (ou 'Criar sequência de 5 follow-ups para reunião' se for fluxo padrão)\n"
                                "   prompt: 'Execute pipedrive_create_task 5 vezes em sequência para criar o plano de negociação/follow-up com <EMPRESA> (deal_id=<ID>):\n"
                                "Tarefa 1: subject=\"<ASSUNTO ESTRETEGICO DA TAREFA 1>\", task_type=\"task\", due_date=\"<HOJE+1d>\", org_name=\"<EMPRESA>\", note=\"<DETALHE COMERCIAL ESTRUTURADO DA TAREFA 1>\"\n"
                                "Tarefa 2: ...'\n\n"
                                "4. ENVIAR PROPOSTA COM DESCONTO / RESPOSTA RÁPIDA: Se o histórico indica que o vendedor (João) prometeu um desconto (ex: 9% de desconto) "
                                "ou que ficou de enviar uma nova proposta e isso ainda não foi formalizado/fechado, sugira uma ação direta de envio por e-mail ou WhatsApp "
                                "com o teor exato da proposta negociada, citando os valores discutidos.\n\n"
                                "5. RESPONDER E-MAIL / WHATSAPP: Se há um e-mail ou thread ativo com entry_id real, ou mensagem do WhatsApp recente sem resposta, "
                                "sugira uma resposta comercialmente impecável, oferecendo resolver a dor do cliente.\n"
                                "   Prompt: 'Execute email_reply com entry_id=[ENTRY_ID_REAL] e body=[TEXTO_DA_RESPOSTA_REAL]' (substitua sempre pelas informações reais coletadas das buscas, nunca use colchetes ou as palavras genéricas no prompt final)\n\n"
                                "NÃO invente IDs. Se não tiver ID real, não use o prompt correspondente.\n"
                                "NÃO escreva nenhum outro texto no seu retorno. Apenas chame suggest_next_actions."
                            ),
                        })
                        continue
                except Exception:
                    pass

            if _final_emitted and not _suggest_actions_done(messages):
                # O dossiê já foi emitido, mas o LLM falhou em gerar o suggest_next_actions.
                # Injetamos ações a partir dos dados reais coletados durante a investigação.
                from datetime import datetime, timedelta
                fallback_actions = []
                today = datetime.now()

                for act in found_activities:
                    fallback_actions.append({
                        "label": f"Concluir atividade pendente · {act['subject']}",
                        "prompt": f"Execute pipedrive_update_task com activity_id={act['id']} e done=true"
                    })

                if found_org:
                    # Detect price objections in messages to customize fallback follow-ups
                    has_price_objection = False
                    objection_keywords = ["caro", "alto", "preço", "preco", "orcamento", "orçamento", "desconto", "concorrencia", "concorrência", "valor"]
                    for _m in messages:
                        _m_content = str(_m.get("content", "")).lower()
                        if any(kw in _m_content for kw in objection_keywords):
                            has_price_objection = True
                            break

                    def _d(delta): return (today + timedelta(days=delta)).strftime("%Y-%m-%d")

                    if has_price_objection:
                        seq_prompt = (
                            f"Execute pipedrive_create_task 5 vezes em sequência para criar o plano de negociação e contorno de objeção de preço com {found_org}"
                            + (f" (deal_id={found_deal_id})" if found_deal_id else "") + ":\n"
                            f"Tarefa 1: subject=\"Estudo interno de margem e engenharia de custos\", task_type=\"task\", due_date=\"{_d(1)}\", org_name=\"{found_org}\", note=\"Analisar viabilidade de concessão de descontos adicionais ou alteração de especificações para caber no orçamento.\"\n"
                            f"Tarefa 2: subject=\"Aviso de revisão de proposta comercial\", task_type=\"task\", due_date=\"{_d(1)}\", org_name=\"{found_org}\", note=\"Enviar mensagem ao contato informando que estamos revisando internamente os valores para apresentar uma alternativa competitiva.\"\n"
                            f"Tarefa 3: subject=\"Enviar proposta comercial revisada\", task_type=\"task\", due_date=\"{_d(3)}\", org_name=\"{found_org}\", note=\"Elaborar e enviar por e-mail ou WhatsApp a proposta com novos preços ou especificações.\"\n"
                            f"Tarefa 4: subject=\"Ligação de acompanhamento consultivo\", task_type=\"call\", due_date=\"{_d(6)}\", org_name=\"{found_org}\", note=\"Ligar para entender o comparativo com a concorrência e o feedback sobre a proposta ajustada.\"\n"
                            f"Tarefa 5: subject=\"Fechamento comercial / alinhamento final\", task_type=\"meeting\", due_date=\"{_d(10)}\", org_name=\"{found_org}\", note=\"Reunião rápida ou ligação para fechar o pedido ou ajustar termos finais de pagamento.\""
                        )
                        lbl = "Criar plano de 5 tarefas de negociação de preço"
                    else:
                        seq_prompt = (
                            f"Execute pipedrive_create_task 5 vezes em sequência para criar o plano de follow-up para agendar reunião com {found_org}"
                            + (f" (deal_id={found_deal_id})" if found_deal_id else "") + ":\n"
                            f"Tarefa 1: subject=\"Follow-up 1: Ligar para {found_org}\", task_type=\"call\", due_date=\"{_d(1)}\", org_name=\"{found_org}\", note=\"Primeira tentativa de contato. Apresentar J.Ferres e propor reunião rápida de 20 min.\"\n"
                            f"Tarefa 2: subject=\"Follow-up 2: Email de apresentação\", task_type=\"task\", due_date=\"{_d(3)}\", org_name=\"{found_org}\", note=\"Enviar e-mail de apresentação propondo reunião. Referenciar último assunto discutido.\"\n"
                            f"Tarefa 3: subject=\"Follow-up 3: Segunda ligação\", task_type=\"call\", due_date=\"{_d(7)}\", org_name=\"{found_org}\", note=\"Segunda tentativa. Perguntar se recebeu o e-mail e verificar disponibilidade.\"\n"
                            f"Tarefa 4: subject=\"Follow-up 4: Canal alternativo (LinkedIn)\", task_type=\"task\", due_date=\"{_d(10)}\", org_name=\"{found_org}\", note=\"Tentar contato via LinkedIn ou outro canal para propor reunião.\"\n"
                            f"Tarefa 5: subject=\"Follow-up 5: Tentativa final\", task_type=\"call\", due_date=\"{_d(14)}\", org_name=\"{found_org}\", note=\"Última tentativa antes de arquivar. Propor horário específico para reunião de 30 min.\""
                        )
                        lbl = "Criar sequência de 5 follow-ups para reunião"

                    fallback_actions.append({
                        "label": lbl,
                        "prompt": seq_prompt,
                    })

                if fallback_actions:
                    _raw_log(process_id, "agent_fallback_suggested_actions", {"actions": fallback_actions})
                    yield _emit({
                        "type": "suggested_actions",
                        "actions": fallback_actions
                    })

            if not _final_emitted:
                _raw_log(process_id, "agent_final_response", {"response": response_text})
                yield _emit({"type": "final", "response": response_text})
            return

        # Separa ferramentas de leitura e escrita
        tool_results = []
        write_tool_pending = None
        read_blocks = []

        for block in tool_use_blocks:
            tool_name = block.get("name", "")
            tool_args = block.get("input") or {}
            tool_id = block.get("id", "")

            if tool_name not in TOOLS:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "tool_name": tool_name,
                    "content": f"Ferramenta '{tool_name}' não encontrada",
                    "is_error": True,
                })
                continue

            # Deduplicação de tool calls — ferramentas de leitura idempotentes não devem
            # ser chamadas mais de uma vez para o MESMO alvo por sessão.
            # Pipedrive (org/persons/deals/activities): chave = tool_name (uma empresa por sessão).
            # Comunicação (whatsapp/email): chave = (tool_name, contato) — permite múltiplos
            # contatos diferentes na mesma sessão (ex: Edvaldo + Lucas + Semorin).
            _DEDUP_PIPEDRIVE = {
                "pipedrive_get_org", "pipedrive_get_persons",
                "pipedrive_get_deals", "pipedrive_get_activities",
            }
            _DEDUP_COMM = {"whatsapp_get_messages", "email_get_contact_history"}
            _DEDUP_READ_TOOLS = _DEDUP_PIPEDRIVE | _DEDUP_COMM

            if tool_name in _DEDUP_READ_TOOLS:
                # Pipedrive: dedup por nome de ferramenta (mesma empresa → mesmo resultado)
                # Comunicação: dedup por (ferramenta, contato) — contatos diferentes = chamadas diferentes
                if tool_name in _DEDUP_PIPEDRIVE:
                    _dedup_key = tool_name
                else:
                    _contact_id = (
                        tool_args.get("contact") or
                        tool_args.get("contact_name") or
                        tool_args.get("org_name") or ""
                    ).lower().strip()
                    _dedup_key = f"{tool_name}:{_contact_id}"

                if _dedup_key in _tool_call_history:
                    log.warning("agent.tool_call.dedup_blocked", tool=tool_name, tool_args=str(tool_args)[:80])
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "tool_name": tool_name,
                        "content": f"[DEDUP] {_dedup_key} já foi executada nesta sessão. Avance para o próximo contato ou ação.",
                        "is_error": False,
                        "summary": f"[já coletado]",
                    })
                    continue

            tool_meta = TOOLS[tool_name]

            # Ferramenta de ESCRITA — sempre exige confirmação do usuário, inclusive em direct_action.
            # O direct_action já foi aprovado pelo usuário (ação sugerida), mas qualquer
            # side-effect externo (enviar email, atualizar CRM, enviar WhatsApp) requer
            # uma segunda confirmação explícita para evitar ações não intencionais.
            if tool_meta["type"] == "write":
                # Ferramentas que exigem investigação completa antes de serem usadas:
                # - Comunicação externa (WhatsApp/Email): precisa de contexto para não enviar mensagem errada
                # - Criação de tarefas (pipedrive_create_task): precisa de contexto para criar tarefas embasadas
                # Ferramentas de CRM simples (update, note) não precisam — são operações de manutenção.
                _INVESTIGATION_REQUIRED = {"whatsapp_send_message", "email_send", "email_reply", "pipedrive_create_task"}
                if tool_name in _INVESTIGATION_REQUIRED:
                    try:
                        _phase = _build_phase_status(messages, query_type=query_type, org_id=org_id)
                        _write_allowed = direct_action or _is_task_action or "Fase final" in _phase or query_type not in ("agent_workflow", "deal_status")
                    except Exception:
                        _write_allowed = True

                    if not _write_allowed:
                        _block_reason = (
                            "criar tarefas embasadas" if tool_name == "pipedrive_create_task"
                            else "enviar mensagens ou emails"
                        )
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "tool_name": tool_name,
                            "content": (
                                f"BLOQUEADO: complete a investigação de comunicação antes de {_block_reason}. "
                                + _phase
                            ),
                            "is_error": False,
                        })
                        continue

                if write_tool_pending is None:
                    call_id = f"tc_{iteration}_{uuid.uuid4().hex[:6]}"
                    write_tool_pending = {
                        "block": block,
                        "call_id": call_id,
                        "label": _get_label(tool_name, tool_args),
                        "prior_results": [],
                        "org_id": org_id,
                    }
                continue  # leituras primeiro

            # Guard: generate_dossier só pode ser chamado quando todas as
            # comunicações foram investigadas (fase 3b ou posterior).
            if tool_name == "generate_dossier":
                try:
                    _gd_phase = _build_phase_status(messages, query_type=query_type, org_id=org_id)
                    _gd_allowed = (
                        _is_task_action
                        or "Todas as fontes foram investigadas" in _gd_phase
                        or "Fase final" in _gd_phase
                        or query_type not in ("agent_workflow", "deal_status")
                    )
                except Exception:
                    _gd_allowed = True
                if not _gd_allowed:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "tool_name": tool_name,
                        "content": (
                            "BLOQUEADO: complete todas as buscas de comunicação antes de consolidar. "
                            + _gd_phase
                        ),
                        "is_error": False,
                    })
                    continue

            executor = tool_meta.get("executor")
            if not executor:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "tool_name": tool_name,
                    "content": "Executor não definido",
                    "is_error": True,
                })
                continue

            call_id = f"tc_{iteration}_{uuid.uuid4().hex[:6]}"
            read_blocks.append((block, call_id, executor))

        # Executa ferramentas de leitura SEQUENCIALMENTE — uma por vez.
        # Se o modelo enviou múltiplas (desobedeceu a instrução), executa a primeira
        # e marca as demais como "skip" para que o modelo as chame individualmente nas
        # próximas iterações. Isso garante que a API receba tool_result para todos os
        # tool_use do turno (obrigatoriedade da spec), sem quebrar o fluxo narrativo.
        if read_blocks:
            first_block, first_call_id, first_executor = read_blocks[0]
            skipped_blocks = read_blocks[1:]

            # Executa a primeira ferramenta
            tool_args = first_block.get("input") or {}
            tool_id = first_block.get("id", "")
            tool_name = first_block.get("name", "")

            # Registra no histórico de dedup SOMENTE a ferramenta que vai executar.
            # As ferramentas em skipped_blocks serão tentadas de novo nas próximas
            # iterações, então NÃO devem ser marcadas como "já executadas" aqui.
            # Registra no histórico de dedup com a chave correta (igual à usada no check acima).
            if tool_name in _DEDUP_READ_TOOLS:
                if tool_name in _DEDUP_PIPEDRIVE:
                    _tool_call_history.add(tool_name)
                else:
                    _exec_contact_id = (
                        tool_args.get("contact") or
                        tool_args.get("contact_name") or
                        tool_args.get("org_name") or ""
                    ).lower().strip()
                    _tool_call_history.add(f"{tool_name}:{_exec_contact_id}")

            yield _emit({"type": "tool_call", "call_id": first_call_id, "tool": tool_name,
                         "args": tool_args, "label": _get_label(tool_name, tool_args)})

            _raw_log(process_id, "tool_execute_start", {"tool": tool_name, "args": tool_args, "call_id": first_call_id})

            try:
                import inspect
                exec_kwargs = {}
                try:
                    sig = inspect.signature(first_executor)
                    params = sig.parameters
                    if "org_id" in params:
                        exec_kwargs["org_id"] = org_id
                    if "messages" in params:
                        exec_kwargs["messages"] = messages
                    if "process_id" in params:
                        exec_kwargs["process_id"] = process_id
                except Exception:
                    pass

                tool_result = await first_executor(tool_args, **exec_kwargs)
                _raw_log(process_id, "tool_execute_result", {"tool": tool_name, "result_raw": tool_result, "call_id": first_call_id})
            except Exception as e:
                tool_result = {"ok": False, "error": str(e)}

            # Retry automático: se a ferramenta falhou por erro transitório, tenta mais uma vez.
            # Não retenta erros esperados como "não encontrado" ou "0 resultados".
            if not tool_result.get("ok"):
                _err = str(tool_result.get("error", "")).lower()
                _expected = any(x in _err for x in [
                    "não encontrad", "not found", "nenhum", "0 contatos", "0 deal",
                    "0 mensagens", "0 e-mail", "sem histórico",
                ])
                if not _expected:
                    try:
                        import asyncio as _asyncio
                        await _asyncio.sleep(1)
                        # Reutiliza exec_kwargs preparados acima
                        tool_result = await first_executor(tool_args, **exec_kwargs)
                    except Exception as e:
                        tool_result = {"ok": False, "error": str(e)}

            ok = tool_result.get("ok", False)
            # Salva o org_id resolvido no estado da sessão para as próximas iterações
            if ok and isinstance(tool_result, dict):
                org_val = tool_result.get("org")
                org_id_from_org = org_val.get("id") if isinstance(org_val, dict) else None
                res_org_id = tool_result.get("org_id") or org_id_from_org
                if res_org_id:
                    try:
                        org_id = int(res_org_id)
                        log.info("agent.session_org_id.updated", org_id=org_id, tool_name=tool_name)
                    except (ValueError, TypeError):
                        pass

            # Captura o dono da tarefa (person_name) antes da sanitização apagar a estrutura
            if ok and tool_name == "pipedrive_get_activities" and not _session_task_person:
                _pending_acts = (tool_result.get("pending") or []) if isinstance(tool_result, dict) else []
                for _a in _pending_acts:
                    if isinstance(_a, dict) and _a.get("person_name"):
                        _session_task_person = _a["person_name"]
                        log.info("agent.session_task_person.set", person=_session_task_person)
                        break

            summary = tool_result.get("summary") or tool_result.get("error") or ("OK" if ok else "Erro")
            yield _emit({"type": "tool_result", "call_id": first_call_id, "tool": tool_name, "summary": summary, "ok": ok})
            yield _emit({"type": "context_saved"})

            if ok and summary:
                _collected_tool_summaries.append(f"[{tool_name}] {summary}")

            if ok and tool_name == "suggest_next_actions":
                actions = tool_result.get("actions", [])
                if actions:
                    yield _emit({"type": "suggested_actions", "actions": actions})

            if ok and tool_name == "open_hierarchy_drawer":
                yield _emit({
                    "type": "hierarchy_mapping_required",
                    "org_name": tool_result.get("org_name"),
                    "org_id": tool_result.get("org_id"),
                    "deal_id": tool_result.get("deal_id"),
                    "activity_id": tool_result.get("activity_id"),
                    "pre_task_id": tool_result.get("pre_task_id"),
                })
                # Para aqui — usuário precisa completar o mapeamento antes de o agente continuar.
                # A continuação é enviada automaticamente quando o worker dispara 'done'.
                if not _final_emitted:
                    _final_emitted = True
                    _org = tool_result.get("org_name", "a empresa")
                    yield _emit({"type": "final", "response": f"Empresa **{_org}** aberta no mapeador. Insira o CNPJ e inicie o mapeamento — assim que terminar, continuarei automaticamente."})
                return

            # Para pipedrive_tasks: gera cards de ação inteligentes direto das atividades.
            # Prompt contextualizado por tipo de tarefa — sem LLM extra.
            if ok and tool_name == "pipedrive_get_all_activities" and query_type == "pipedrive_tasks":
                _pd_actions = []
                for _act in tool_result.get("overdue", []):
                    _subj = _act.get("subject") or ""
                    _org = _act.get("org") or ""
                    _act_id = _act.get("id")
                    if not _act_id:
                        continue
                    _pd_actions.append({
                        "label": f"⚠️ ATRASADA → {_subj}" + (f"  ·  {_org}" if _org else ""),
                        "prompt": _build_task_action_prompt(
                            _act_id, _subj, _org,
                            _act.get("org_id"), _act.get("deal_id"),
                            _act.get("type", ""), _act.get("note", "")
                        ),
                    })
                for _act in tool_result.get("today", []):
                    _subj = _act.get("subject") or ""
                    _org = _act.get("org") or ""
                    _act_id = _act.get("id")
                    if not _act_id:
                        continue
                    _pd_actions.append({
                        "label": f"{_subj}" + (f"  →  {_org}" if _org else ""),
                        "prompt": _build_task_action_prompt(
                            _act_id, _subj, _org,
                            _act.get("org_id"), _act.get("deal_id"),
                            _act.get("type", ""), _act.get("note", "")
                        ),
                    })
                if _pd_actions:
                    yield _emit({"type": "suggested_actions", "actions": _pd_actions})

            sanitized = _sanitize_result(tool_name, tool_result)
            raw_content = json.dumps(sanitized, ensure_ascii=False)
            # Limite de truncação dinâmico: atividades globais e emails precisam de mais espaço
            _max_content = 4000 if tool_name in ("pipedrive_get_all_activities", "email_get_inbox", "email_get_contact_history") else 2000
            if len(raw_content) > _max_content:
                raw_content = raw_content[:_max_content] + "... [TRUNCADO]"

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "tool_name": tool_name,
                "content": raw_content,
            })

            # Marca ferramentas extras como skipped (protocolo exige tool_result para todas)
            for skip_block, skip_call_id, _ in skipped_blocks:
                skip_tool_id = skip_block.get("id", "")
                skip_tool_name = skip_block.get("name", "")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": skip_tool_id,
                    "tool_name": skip_tool_name,
                    "content": "SKIPPED: chame apenas uma ferramenta por vez. Chame esta ferramenta individualmente na próxima resposta.",
                    "is_error": False,
                })

        # Pausa para ferramenta de escrita (leituras já foram executadas)
        if write_tool_pending:
            action_id = str(uuid.uuid4())
            block = write_tool_pending["block"]
            tool_name = block["name"]
            tool_args = block["input"]

            messages_with_assistant = messages + [{"role": "assistant", "content": content}]

            _PENDING[action_id] = {
                "tool_use_id": block["id"],
                "tool": tool_name,
                "args": tool_args,
                "call_id": write_tool_pending["call_id"],
                "label": write_tool_pending["label"],
                "messages_snapshot": messages_with_assistant,
                "prior_results": tool_results,  # inclui resultados das leituras paralelas
                "iteration": iteration + 1,
                "org_id": write_tool_pending.get("org_id"),
                "process_id": process_id,
                "parent_message_id": parent_message_id,
                "action_index": action_index,
            }

            label_fn = TOOLS[tool_name].get("confirm_label")
            confirm_label = label_fn(tool_args) if callable(label_fn) else write_tool_pending["label"]
            preview = tool_args.get("message") or tool_args.get("body") or json.dumps(tool_args, ensure_ascii=False)[:120]

            yield _emit({
                "type": "confirmation_required",
                "action_id": action_id,
                "tool": tool_name,
                "label": confirm_label,
                "preview": str(preview),
                "args": tool_args,
            })
            return

        # Todos os tool calls processados — adiciona ao histórico e continua
        # Adiciona a resposta do assistente (chamada de ferramenta)
        messages.append({"role": "assistant", "content": content, "tool_use_id": [b["id"] for b in tool_use_blocks] if tool_use_blocks else None})
        
        # Adiciona os resultados usando o formato de lista de objetos que o _messages_to_openai entende
        messages.append({"role": "user", "content": tool_results})

    # Esgotou iterações
    yield _emit({
        "type": "final",
        "response": "Não consegui concluir a tarefa dentro do número máximo de passos. Tente reformular o pedido.",
    })

