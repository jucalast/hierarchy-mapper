"""
Executor de ações de WhatsApp e Email.
Resolve contatos, envia mensagens e busca históricos.
"""
import httpx
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession


async def execute_whatsapp_action(
    intent_info: dict,
    session: AsyncSession
) -> Optional[Dict[str, Any]]:
    """
    Executa a ação de WhatsApp detectada pelo classificador de intenção.
    Retorna o contexto de resultado para injeção no pipeline.
    """
    action = intent_info.get("whatsapp_action")
    if not action:
        return None
    
    print(f"[AI Chat] Executando Ação WhatsApp Automática: {action}")
    
    whatsapp_result_context = None
    
    try:
        from services.whatsapp_resolver import WhatsAppResolverService
        
        wa_base = "http://localhost:8001/api/whatsapp"
        async with httpx.AsyncClient(timeout=20.0) as client:
            
            # RESOLUÇÃO INTELIGENTE DE CONTATO
            chat_id = intent_info.get("whatsapp_chat_id")
            target_number = intent_info.get("whatsapp_number")
            
            # Se não tem ID nem número, mas tem dicas de nome/empresa/hint -> RESOLVER
            if not chat_id and not target_number and (
                intent_info.get("extracted_company_name") or 
                intent_info.get("extracted_person_name") or 
                intent_info.get("extracted_person_hint")
            ):
                print(f"[AI Chat] Tentando resolução inteligente de contato...")
                resolution = await WhatsAppResolverService.resolve_contact(
                    session,
                    company_name=intent_info.get("extracted_company_name"),
                    person_name=intent_info.get("extracted_person_name"),
                    person_hint=intent_info.get("extracted_person_hint")
                )
                if resolution.get("success"):
                    chat_id = resolution.get("chat_id")
                    best_match = resolution.get("best_match", {})
                    print(f"[AI Chat] Contato resolvido: {best_match.get('name')} ({chat_id})")
                    
                    # Tentar buscar Foto Real do WhatsApp (prioridade)
                    wa_picture = None
                    try:
                        clean_num = chat_id.split('@')[0]
                        if not clean_num.startswith('55') and len(clean_num) >= 10:
                            clean_num = f"55{clean_num}"
                            
                        async with httpx.AsyncClient(timeout=3.0) as wa_pic_client:
                            wa_pic_url = f"http://localhost:8001/api/whatsapp/contacts/by-number/{clean_num}/profile-pic"
                            wa_resp = await wa_pic_client.get(wa_pic_url)
                            if wa_resp.status_code == 200:
                                wa_picture = wa_resp.json().get("profilePicUrl")
                                print(f"[WA Pic] Foto real encontrada: {wa_picture[:50]}...")
                    except Exception as wa_pic_err:
                        print(f"[WA Pic] Erro ao buscar foto real: {wa_pic_err}")

                    # DETECÇÃO DE AMBIGUIDADE
                    all_matches = resolution.get("all_matches", [])
                    is_ambiguous = False
                    if len(all_matches) > 1:
                        # Se o segundo match tem confiança muito próxima do primeiro
                        if all_matches[0]["confidence"] - all_matches[1]["confidence"] < 10:
                            is_ambiguous = True
                    
                    if is_ambiguous:
                        print(f"[AI Chat] ⚠️ Ambiguidade detectada: {len(all_matches)} contatos similares.")
                        whatsapp_result_context = {
                            "error": "AMBIGUOUS_CONTACT",
                            "status": 400,
                            "matches": all_matches[:3],
                            "extracted_name": intent_info.get("extracted_person_name")
                        }
                        # Forçamos chat_id para None para não tentar o envio às cegas
                        chat_id = None
                    else:
                        whatsapp_result_context = {
                            "whatsapp_action": action,
                            "resolved_contact": best_match,
                            "contact_picture": wa_picture or best_match.get("profilePicture") or best_match.get("picture_url")
                        }
            
            if action == "send_message":
                whatsapp_result_context = await _execute_send_message(
                    client, wa_base, intent_info, chat_id, target_number, whatsapp_result_context
                )
                    
            elif action == "get_chats":
                resp = await client.get(f"{wa_base}/chats")
                whatsapp_result_context = {"whatsapp_action": action, "status": resp.status_code, "resultado": resp.json()}
                
            elif action == "get_messages":
                whatsapp_result_context = await _execute_get_messages(
                    client, wa_base, intent_info, chat_id, whatsapp_result_context
                )
                    
            elif action == "search_contacts":
                search_name = intent_info.get("extracted_person_name") or intent_info.get("extracted_company_name")
                if search_name:
                    resp = await client.get(f"{wa_base}/contacts/search?name={search_name}")
                else:
                    resp = await client.get(f"{wa_base}/contacts/all")
                whatsapp_result_context = {"whatsapp_action": action, "status": resp.status_code, "resultado": resp.json()}
            else:
                whatsapp_result_context = {"error": f"Ação {action} desconhecida"}
    except Exception as e:
        print(f"[AI Chat] Erro ao conectar com WhatsApp Service: {e}")
        whatsapp_result_context = {"error": f"WhatsApp Service offline ou erro de conexão: {str(e)}"}
    
    return whatsapp_result_context


async def _execute_send_message(client, wa_base, intent_info, chat_id, target_number, whatsapp_result_context):
    """Executa a ação de envio de mensagem WhatsApp."""
    action = "send_message"
    
    # Se já temos um chat_id (ID completo com @c.us ou @lid), usamos ele integralmente
    if chat_id and ("@" in str(chat_id)):
        valid_suffixes = ["@c.us", "@lid", "@g.us"]
        if any(suffix in str(chat_id) for suffix in valid_suffixes):
            number_to_send = chat_id
            number_str = chat_id
        else:
            print(f"[AI Chat] ⚠️ Descartando ID inválido (provável nome): {chat_id}")
            number_to_send = None
    else:
        number_to_send = target_number or (chat_id.split('@')[0] if chat_id else None)
        if number_to_send:
            number_str = str(number_to_send).strip().replace("+", "").replace(" ", "").replace("-", "")
            if len(number_str) <= 11 and not number_str.startswith("55"):
                number_str = f"55{number_str}"
        else:
            number_str = None
    
    if number_to_send:
        msg_text = intent_info.get("whatsapp_message")
        if msg_text and len(msg_text.strip()) > 0:
            resp = await client.post(f"{wa_base}/send", json={"number": number_str, "message": msg_text})
            res_data = resp.json()
            # Prepara dados para o preview no front
            send_ctx = {
                "whatsapp_action": action, 
                "status": resp.status_code, 
                "resultado": res_data,
                "sent_message": msg_text,
                "contact": whatsapp_result_context.get("resolved_contact") if whatsapp_result_context else {"id": number_str, "name": intent_info.get("extracted_person_name") or "Contato"}
            }
            if whatsapp_result_context:
                whatsapp_result_context.update(send_ctx)
            else:
                whatsapp_result_context = send_ctx
            print(f"[AI Chat] ✅ Mensagem enviada para {number_str}")
        else:
            print(f"[AI Chat] ⚠️ Mensagem vazia. Solicitando conteúdo ao usuário.")
            whatsapp_result_context = {
                "error": "MISSING_MESSAGE_BODY", 
                "contact_name": intent_info.get("extracted_person_name") or "o contato",
                "target_number": number_str
            }
    elif not whatsapp_result_context or "error" not in whatsapp_result_context:
        # Só entra aqui se NÃO houve erro prévio (como AMBIGUIDADE)
        print(f"[AI Chat] ❌ Falha: número não identificado para '{intent_info.get('extracted_person_name')}'")
        whatsapp_result_context = {
            "error": "CONTACT_NOT_FOUND", 
            "contact_name": intent_info.get("extracted_person_name") or "o contato",
            "whatsapp_action": action
        }
    
    return whatsapp_result_context


async def _execute_get_messages(client, wa_base, intent_info, chat_id, whatsapp_result_context):
    """Executa a ação de busca de mensagens WhatsApp."""
    action = "get_messages"
    
    # PRIORIDADE 1: Se já temos um chat_id resolvido (ID formatado como @c.us ou @lid), usa ele direto
    resolved_chat_id = chat_id
    if not resolved_chat_id and whatsapp_result_context and "resolved_contact" in whatsapp_result_context:
        rc = whatsapp_result_context["resolved_contact"]
        resolved_chat_id = rc.get("id") or rc.get("id", {}).get("_serialized")
    
    if resolved_chat_id and ("@" in str(resolved_chat_id)):
        print(f"[AI Chat] Buscando mensagens pelo ID Resolvido: {resolved_chat_id}")
        resp = await client.get(f"{wa_base}/chats/{resolved_chat_id}/messages?limit=30")
        res_data = resp.json()
        if whatsapp_result_context:
            whatsapp_result_context.update({"whatsapp_action": action, "status": resp.status_code, "resultado": res_data})
        else:
            whatsapp_result_context = {"whatsapp_action": action, "status": resp.status_code, "resultado": res_data}
    
    # PRIORIDADE 2: Se temos um número de telefone puro
    else:
        target_number = intent_info.get("whatsapp_number")
        if not target_number and whatsapp_result_context and "resolved_contact" in whatsapp_result_context:
            rc = whatsapp_result_context["resolved_contact"]
            target_number = rc.get("number") or rc.get("phone")
        
        if target_number:
            # Limpa o número (Removendo também parênteses)
            num_str = str(target_number).split('@')[0].replace("+", "").replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
            
            # Normalização Brasil (Garante prefixo 55 se faltar)
            if len(num_str) in [10, 11] and not num_str.startswith("55"):
                num_str = f"55{num_str}"
                
            print(f"[AI Chat] Buscando mensagens pelo número de telefone: {num_str}")
            resp = await client.get(f"{wa_base}/chats/by-number/{num_str}/messages?limit=30")
            res_data = resp.json()
            if whatsapp_result_context:
                whatsapp_result_context.update({"whatsapp_action": action, "status": resp.status_code, "resultado": res_data})
            else:
                whatsapp_result_context = {"whatsapp_action": action, "status": resp.status_code, "resultado": res_data}
        elif chat_id:
            # Fallback para qualquer chat_id que sobrou
            resp = await client.get(f"{wa_base}/chats/{chat_id}/messages?limit=30")
            res_data = resp.json()
            if whatsapp_result_context:
                whatsapp_result_context.update({"whatsapp_action": action, "status": resp.status_code, "resultado": res_data})
            else:
                whatsapp_result_context = {"whatsapp_action": action, "status": resp.status_code, "resultado": res_data}
        else:
            whatsapp_result_context = {"error": "Não consegui identificar de qual conversa você está falando."}
    
    return whatsapp_result_context


async def execute_email_action(intent_info: dict) -> Optional[Dict[str, Any]]:
    """
    Executa a ação de email detectada pelo classificador de intenção.
    Retorna o contexto de resultado para injeção no pipeline.
    """
    action = intent_info.get("email_action")
    if not action:
        return None
    
    print(f"[AI Chat] Executando Ação Email Automática: {action}")
    
    email_result_context = None
    
    try:
        email_base = "http://localhost:8002/api/email"
        async with httpx.AsyncClient(timeout=30.0) as client_http:
            
            if action == "send_email":
                to = intent_info.get("email_to")
                subject = intent_info.get("email_subject") or "Mensagem de Contato"
                body = intent_info.get("email_body")
                
                if to and body:
                    resp = await client_http.post(f"{email_base}/send", json={
                        "to": to, "subject": subject, "body": body
                    })
                    res_data = resp.json()
                    email_result_context = {
                        "email_action": "send_email",
                        "status": resp.status_code,
                        "to": to,
                        "subject": subject,
                        "sent_message": body,
                        "contact": {"id": to, "email": to, "name": intent_info.get("extracted_person_name") or to},
                        "resultado": res_data
                    }
                    print(f"[AI Chat] ✅ Email enviado para {to}")
                else:
                    email_result_context = {
                        "error": "Destinatário ou corpo do email ausente.", 
                        "email_action": action
                    }
            
            elif action == "list_folders":
                resp = await client_http.get(f"{email_base}/folders")
                email_result_context = {"email_action": action, "status": resp.status_code, "folders": resp.json().get("folders", [])}
                
            elif action == "get_messages" or action == "get_unread":
                folder = intent_info.get("email_folder") or "Inbox"
                endpoint = "unread" if action == "get_unread" else "messages"
                resp = await client_http.get(f"{email_base}/{endpoint}?folder={folder}&limit=10")
                email_result_context = {"email_action": action, "status": resp.status_code, "folder": folder, "resultado": resp.json()}

    except Exception as e:
        print(f"[AI Chat] Erro ao conectar com Email Service: {e}")
        email_result_context = {"error": f"Email Service offline: {str(e)}"}
    
    return email_result_context
