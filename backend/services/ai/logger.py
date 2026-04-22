import os
import json
from datetime import datetime

def dump_intelligence_context(message: str, intent_info: dict, context: dict, org_id: int = None):
    """
    Gera um dump detalhado do contexto bruto usado pela IA para formular a resposta.
    Salvo em backend/logs/intelligence_raw_context.md para auditoria.
    """
    try:
        log_dir = "backend/logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        log_path = os.path.join(log_dir, "intelligence_raw_context.md")
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"# 🧠 Raw Intelligence Context Dump\n")
            f.write(f"**Data/Hora**: {timestamp}\n\n")
            
            f.write(f"## 💬 Entrada do Usuário\n")
            f.write(f"```text\n{message}\n```\n\n")
            
            f.write(f"## 🎯 Intenção e Metadados\n")
            f.write(f"- **Tipo de Query**: {intent_info.get('query_type')}\n")
            f.write(f"- **ID Organização**: {org_id}\n")
            f.write(f"- **Escopos de Dados**: {intent_info.get('data_scope')}\n")
            f.write(f"- **Entidades Selecionadas (UI)**: {json.dumps(context.get('selected_entities', []), indent=2)}\n\n")
            
            # 1. Pipedrive Data
            f.write(f"## 🔗 Dados do Pipedrive (Brutos)\n")
            pd_data = {
                "deals": context.get("deals", []),
                "activities": context.get("activities", []),
                "notes": context.get("notes", []),
                "persons": context.get("persons", [])
            }
            f.write(f"```json\n{json.dumps(pd_data, indent=2, ensure_ascii=False)}\n```\n\n")
            
            # 2. WhatsApp Data
            f.write(f"## 💬 Mensagens do WhatsApp\n")
            wa_res = context.get("whatsapp_result", {}).get("resultado", {})
            wa_groups = wa_res.get("messages_by_contact", [])
            
            if wa_groups:
                for group in wa_groups:
                    f.write(f"### 📱 Contato: {group.get('contact')}\n")
                    msgs = group.get("messages", [])
                    if msgs:
                        f.write(f"```json\n{json.dumps(msgs, indent=2, ensure_ascii=False)}\n```\n")
                    else:
                        f.write("_Nenhuma mensagem encontrada para este contato._\n")
                    f.write("\n")
            else:
                f.write("_Nenhuma mensagem de WhatsApp encontrada/solicitada._\n")
            f.write("\n")
            
            # 3. Email Data
            f.write(f"## 📧 Threads de Email (Outlook)\n")
            email_res = context.get("email_result", {}).get("resultado", {})
            email_groups = email_res.get("messages_by_contact", [])
            
            if email_groups:
                for group in email_groups:
                    f.write(f"### 👤 Contato: {group.get('contact')} ({group.get('email')})\n")
                    
                    human = group.get("human_threads", [])
                    if human:
                        f.write(f"**Threads Humanas ({len(human)}):**\n")
                        f.write(f"```json\n{json.dumps(human, indent=2, ensure_ascii=False)}\n```\n")
                    else:
                        f.write("_Nenhuma linha de comunicação humana direta encontrada._\n")
                    
                    auto_count = group.get("automated_count", 0)
                    if auto_count > 0:
                        f.write(f"\n⚠️ **Automações Descartadas**: {auto_count} e-mails (Marketing/Sistema) foram analisados e removidos do prompt final para evitar ruído.\n")
                    f.write("\n")
            else:
                f.write("_Nenhum e-mail encontrado para os contatos pesquisados._\n")
            f.write("\n")
            
            # 4. Contexto Adicional (OSINT, etc)
            f.write(f"## 🛠️ Contexto Adicional (Enriquecimento)\n")
            other = {k: v for k, v in context.items() if k not in ["deals", "activities", "notes", "persons", "whatsapp", "emails"]}
            f.write(f"```json\n{json.dumps(other, indent=2, ensure_ascii=False)}\n```\n\n")
            
            f.write(f"---\n_Este arquivo é sobrescrito a cada nova pergunta para servir como log de tempo real._\n")
            
        print(f"[Intelligence Log] ✅ Raw context dumped to {log_path}")
    except Exception as e:
        print(f"[Intelligence Log] ❌ Erro ao gerar dump: {e}")
