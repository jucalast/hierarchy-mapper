"""
Funções utilitárias do Agente.
  _emit                  — serializa evento NDJSON
  _raw_log               — log estruturado em arquivo
  _fix_corrupted_name    — corrige nomes corrompidos pelo tokenizador Llama
  _get_thinking_fallback — texto de reasoning contextual padrão por ferramenta
  _get_label             — label legível para chamadas de ferramenta
"""
from __future__ import annotations
import json
from typing import Any

def _emit(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False) + "\n"


def _raw_log(process_id: str, event_type: str, data: Any):
    """Loga dados brutos e estruturados para depuração profunda do Agente V2."""
    try:
        import os
        import json
        from datetime import datetime
        
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # Tenta usar o diretório que o usuário prefere (backend/backend/logs)
        log_dir = os.path.abspath(os.path.join(current_dir, "..", "..", "..", "backend", "logs"))
        if not os.path.exists(log_dir):
            log_dir = os.path.abspath(os.path.join(current_dir, "..", "..", "..", "logs"))
        
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
            
        # 1. Log NDJSON (para processamento e auditoria técnica)
        ndjson_file = os.path.join(log_dir, "agent_raw.log")
        entry = {
            "timestamp": datetime.now().isoformat(),
            "process_id": process_id,
            "event": event_type,
            "data": data
        }
        with open(ndjson_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
            
        # 2. Log Markdown (estruturadinho para leitura humana direta)
        md_file = os.path.join(log_dir, "agent_debug.md")
        md_mode = "w" if event_type == "agent_start" else "a"
        with open(md_file, md_mode, encoding="utf-8") as f:
            if event_type == "agent_start":
                f.write(f"# 🕵️ Investigação: {process_id} ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})\n")
                f.write(f"**Mensagem Original**: `{data.get('message')}`\n")
                f.write(f"**Org ID**: `{data.get('org_id')}` | **Preferência**: `{data.get('preferred')}`\n")
                f.write("\n---\n")
            
            elif event_type == "llm_request":
                f.write(f"\n## 🔄 Turno {data.get('iteration')}\n")
                f.write("### 🤖 Chamada LLM\n")
                f.write("<details><summary><b>System Prompt</b> (clique para expandir)</summary>\n\n")
                f.write(f"```text\n{data.get('system')}\n```\n</details>\n\n")
                
                # Mostra apenas as últimas 2 mensagens para não poluir o MD
                messages = data.get("messages", [])
                if messages:
                    f.write("**Contexto Recente do Histórico**:\n")
                    for m in messages[-2:]:
                        role = m.get("role", "unknown")
                        content = m.get("content", "")
                        # Se content for lista (tool results), formata bonito
                        if isinstance(content, list):
                            content_str = json.dumps(content, indent=2, ensure_ascii=False)
                        else:
                            content_str = str(content)
                        f.write(f"- **{role.upper()}**:\n```json\n{content_str}\n```\n")
            
            elif event_type == "llm_response":
                f.write("### 📥 Resposta Bruta do Modelo\n")
                f.write("```json\n" + json.dumps(data.get("response"), indent=2, ensure_ascii=False) + "\n```\n")
            
            elif event_type == "tool_execute_start":
                f.write(f"#### 🛠️ Executando: `{data.get('tool')}`\n")
                f.write(f"**Argumentos**: `{json.dumps(data.get('args'), ensure_ascii=False)}`\n")
            
            elif event_type == "tool_execute_result":
                f.write(f"#### 📦 Resultado da Ferramenta: `{data.get('tool')}`\n")
                res_raw = data.get("result_raw")
                res_str = json.dumps(res_raw, indent=2, ensure_ascii=False, default=str)
                # Trunca se for gigantesco para não travar o editor do usuário
                if len(res_str) > 10000:
                    res_str = res_str[:10000] + "\n... [TRUNCADO NO PREVIEW]"
                f.write("```json\n" + res_str + "\n```\n")
                f.write("\n---\n")
            
            elif event_type == "agent_final_response":
                f.write("\n## 🏁 Dossiê / Resposta Final\n")
                f.write(f"{data.get('response')}\n")
                f.write(f"\n**Status**: Concluído em {datetime.now().strftime('%H:%M:%S')}\n")
                f.write("\n" + "="*80 + "\n")
                
            elif event_type == "agent_error":
                 f.write(f"\n## ❌ ERRO NO PROCESSO\n")
                 f.write(f"```text\n{data.get('content')}\n```\n")

    except Exception:
        # Silencioso para não quebrar o fluxo principal
        pass


def _fix_corrupted_name(name: str, fallback: str = "a empresa") -> str:
    """Detecta e corrige nomes corrompidos pelo tokenizador Llama (ex: 'Colch9es' -> 'Colchões') com fallback."""
    if not name:
        return fallback
    import re as _re
    # 1. Caso com "es" no final (ex: 'Colch9es' -> 'Colchões')
    repaired = _re.sub(r'Colch\d+(\s+\d+)?es', 'Colchões', name, flags=_re.IGNORECASE)
    # 2. Caso geral sem "es" ou com espaços (ex: 'Colch43 147453541' -> 'Colchões')
    repaired = _re.sub(r'Colch\d+(\s+\d+)?', 'Colchões', repaired, flags=_re.IGNORECASE)
    # 3. Caso genérico para outras palavras terminadas em \d+es (ex: 'Solu9es' -> 'Solucoes')
    repaired = _re.sub(r'([a-zA-Z]+)\d+es', r'\1oes', repaired)
    
    return repaired or fallback


def _get_tools_called(messages: list, target_tools: set[str] | None = None) -> set[str]:
    """Extrai de forma robusta todos os nomes de ferramentas chamadas com sucesso no histórico.
    Lida com content em formato list (tool blocks) ou string (JSON serializado do DB)."""
    import json
    import ast
    tools = set()

    for m in messages:
        content = m.get("content", "")
        blocks = []
        
        if isinstance(content, list):
            blocks = content
        elif isinstance(content, str):
            content_trimmed = content.strip()
            if content_trimmed.startswith("[") or content_trimmed.startswith("{"):
                try:
                    blocks = json.loads(content_trimmed)
                except Exception:
                    try:
                        blocks = ast.literal_eval(content_trimmed)
                    except Exception:
                        pass
        
        if not isinstance(blocks, list):
            # Se for um único dicionário (bloco individual)
            if isinstance(blocks, dict):
                blocks = [blocks]
            else:
                continue

        for b in blocks:
            if not isinstance(b, dict):
                continue
            
            # Captura de tool_use (o que o assistente pediu)
            if b.get("type") == "tool_use":
                tn = b.get("name")
                if tn:
                    if target_tools is None or tn in target_tools:
                        tools.add(tn)
            
            # Captura de tool_result (o que efetivamente retornou ok)
            elif b.get("type") == "tool_result":
                tn = b.get("tool_name")
                # Só considera "feito" se não for erro
                if tn and not b.get("is_error"):
                    if target_tools is None or tn in target_tools:
                        tools.add(tn)
                        
    return tools


def _get_thinking_fallback(tool_name: str, args: dict) -> str:
    """Thinking mínimo contextual quando o modelo não gera texto e o auxiliar falha.
    Diferente do _get_label — explica o raciocínio, não só o que está sendo feito."""
    if not args:
        args = {}
    org = _fix_corrupted_name(args.get("org_name", ""), "a empresa")
    contact = args.get("contact") or args.get("contact_name") or "o contato"
    templates = {
        "pipedrive_get_org":
            f"Vou verificar os dados de {org} no CRM para entender o contexto do negócio.",
        "pipedrive_get_persons":
            f"Buscando os contatos responsáveis em {org} para identificar os decisores.",
        "pipedrive_get_deals":
            f"Analisando os negócios em aberto de {org} para ver o estágio atual.",
        "pipedrive_get_activities":
            f"Verificando o histórico de tarefas e compromissos com {org}.",
        "whatsapp_get_messages":
            f"Recuperando conversas recentes com {contact} para alinhar o discurso.",
        "email_get_contact_history":
            f"Analisando histórico de e-mails de {contact} para complementar a visão.",
        "generate_dossier":
            "Consolidando toda a investigação em um dossiê estratégico.",
        "evaluate_prospects":
            f"Avaliando quais perfis em {org} são os melhores para abordar agora.",
        "deep_company_investigation":
            f"Realizando pesquisa externa e OSINT para enriquecer os dados de {org}.",
    }
    return templates.get(tool_name, f"Verificando {tool_name.replace('_', ' ')} para prosseguir.")


def _get_label(tool_name: str, args: dict) -> str:
    args = args or {}
    _org = _fix_corrupted_name(args.get('org_name', ''), '...')
    labels = {
        "whatsapp_get_messages": f"Buscando mensagens de {args.get('contact', '...')}",
        "whatsapp_list_chats": "Listando chats do WhatsApp",
        "whatsapp_send_message": f"Enviar mensagem para {args.get('contact', '...')}",
        "pipedrive_get_org": f"Consultando {_org} no Pipedrive",
        "pipedrive_get_persons": f"Buscando contatos de {_org}",
        "pipedrive_get_deals": f"Buscando deals de {_org}",
        "pipedrive_get_activities": f"Buscando atividades de {_org}",
        "pipedrive_get_all_activities": "Buscando todas as atividades de hoje e atrasadas",
        "pipedrive_update_deal": f"Atualizando deal #{args.get('deal_id') if args.get('deal_id') else '(aberto da empresa)'}",
        "pipedrive_create_task": f"Criar tarefa: {args.get('subject', '...')}",
        "pipedrive_update_task": f"Atualizando atividade #{args.get('activity_id', '...')}",
        "pipedrive_create_note": f"Adicionando nota ao Pipedrive",
        "email_get_inbox": "Acessando caixa de entrada",
        "email_get_contact_history": f"Buscando e-mails de {args.get('contact_name') or args.get('org_name') or args.get('contact_email') or '...'}",
        "email_send": f"Enviar e-mail para {args.get('to', '...')}",
        "email_reply": f"Responder e-mail de {args.get('contact_name', '...')}",
        "web_search_external": f"Pesquisando: {args.get('query', '...')}",
    }
    return labels.get(tool_name, tool_name)

