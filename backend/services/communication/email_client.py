import os
import time
import random
from typing import List, Dict, Optional

# Tenta importar win32com para a "mágica" do Windows/Outlook
try:
    import win32com.client
    import pythoncom
    import re
    import unicodedata
    HAS_PYWIN32 = True
except ImportError:
    HAS_PYWIN32 = False
    import re
    import unicodedata
    import smtplib
    import imaplib
    import email
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

class EmailClient:
    """
    Cliente de email que utiliza integração direta com o Outlook (via pywin32) no Windows,
    ou SMTP/IMAP tradicional como fallback ou em outros sistemas.
    """
    
    SMTP_SERVER = "smtp.office365.com"
    SMTP_PORT = 587
    IMAP_SERVER = "outlook.office365.com"
    IMAP_PORT = 993
    
    def __init__(self, email_address=None, password=None, use_outlook_app=True):
        self.email_address = email_address or os.getenv("EMAIL_USER") or "joao.moura@jferres.com.br"
        self.password = password or os.getenv("EMAIL_PASSWORD")
        self.use_outlook_app = use_outlook_app and HAS_PYWIN32
        
        if self.use_outlook_app:
            print("[EmailClient] Usando integração direta com Outlook Desktop (Mágica)")
            # Tenta inicializar uma vez para garantir que o COM está ok
            try:
                pythoncom.CoInitialize()
                self._get_outlook_instance()
            except:
                pass
        elif not self.password:
            print("[EmailClient] Warning: EMAIL_PASSWORD não configurado para uso de SMTP")

    def _get_outlook_instance(self):
        """
        Tenta pegar uma instância já aberta do Outlook ou cria uma nova de forma silenciosa.
        """
        if not HAS_PYWIN32: return None
        
        try:
            # Tenta pegar instância já aberta (evita disparar lembretes se já estiver aberto)
            try:
                outlook = win32com.client.GetActiveObject("Outlook.Application")
            except:
                # Se não houver, cria uma nova
                outlook = win32com.client.Dispatch("Outlook.Application")
            
            # Tenta forçar silêncio no Logon
            try:
                ns = outlook.GetNamespace("MAPI")
                # Logon(ProfileName, Password, ShowDialog, NewSession)
                # ShowDialog=False evita popups de seleção de perfil
                ns.Logon("", "", False, False)
            except:
                pass
                
            return outlook
        except Exception as e:
            print(f"[EmailClient] Erro ao obter instância do Outlook: {e}")
            return None

    def send_outbound_email(self, to_email: str, subject: str, html_body: str, tracking_id: Optional[str] = None, request_read_receipt: bool = False):
        """
        Envia e-mail via Outlook App ou SMTP com suporte a Recibo de Leitura.
        """
        # Delay humano
        time.sleep(random.uniform(1.0, 2.5))

        # Limpeza básica do e-mail (remove menções ou espaços acidentais)
        if to_email:
            to_email = to_email.strip().lstrip("@")

        # Injetar Pixel de Rastreio
        final_body = html_body
        if tracking_id:
            tracking_url = f"{os.getenv('API_BASE_URL', 'http://127.0.0.1:8000')}/api/v1/communication/track?id={tracking_id}"
            pixel_html = f'<img src="{tracking_url}" width="1" height="1" style="display:none;" />'
            final_body = html_body + pixel_html

        if self.use_outlook_app:
            try:
                pythoncom.CoInitialize()
                outlook = self._get_outlook_instance()
                if not outlook: raise Exception("Não foi possível conectar ao Outlook")
                
                mail = outlook.CreateItem(0) # 0 = olMailItem
                mail.To = to_email
                mail.Subject = subject
                
                # Mágica para pegar a ASSINATURA OFICIAL do Outlook:
                # Se o corpo JÁ contém a assinatura (marcada pelo Agente), não duplicamos.
                if "<!-- SIGNATURE_START -->" in final_body:
                    # Removemos apenas os comentários de marcação antes de enviar
                    mail.HTMLBody = final_body.replace("<!-- SIGNATURE_START -->", "").replace("<!-- SIGNATURE_END -->", "")
                else:
                    # Caso contrário, força o Outlook a inserir a assinatura padrão
                    mail.Display()
                    time.sleep(0.5)
                    signature_html = mail.HTMLBody
                    mail.HTMLBody = final_body + signature_html
                
                if request_read_receipt:
                    mail.ReadReceiptRequested = True
                
                # Selecionar conta correta
                if self.email_address:
                    for account in outlook.Session.Accounts:
                        if account.SmtpAddress.lower() == self.email_address.lower():
                            mail._oleobj_.Invoke(*(64209, 0, 8, 0, account)) # SendUsingAccount
                            break
                
                mail.Send()
                print(f"[EmailClient] SUCCESS: E-mail enviado via Outlook App para {to_email}")
                return True
            except Exception as e:
                print(f"[EmailClient] ERROR (Outlook App): {e}")
                return False
        else:
            # Fallback SMTP
            msg = MIMEMultipart()
            msg['From'] = self.email_address
            msg['To'] = to_email
            msg['Subject'] = subject
            msg.attach(MIMEText(final_body, 'html'))

            try:
                server = smtplib.SMTP(self.SMTP_SERVER, self.SMTP_PORT)
                server.starttls()
                server.login(self.email_address, self.password)
                server.send_message(msg)
                server.quit()
                print(f"[EmailClient] SUCCESS: E-mail enviado via SMTP para {to_email}")
                return True
            except Exception as e:
                print(f"[EmailClient] ERROR (SMTP): {e}")
                return False

    def reply_to_email(self, entry_id: str, html_body: str, reply_all: bool = True):
        """
        Responde a um e-mail específico mantendo a Thread (In-Reply-To).
        """
        if not self.use_outlook_app:
            print("[EmailClient] Resposta encadeada (Reply) só é suportada via Outlook Desk.")
            return False

        try:
            pythoncom.CoInitialize()
            outlook = self._get_outlook_instance()
            if not outlook: return False

            # Localiza a mensagem original
            try:
                namespace = outlook.GetNamespace("MAPI")
                original_msg = namespace.GetItemFromID(entry_id)
            except Exception as e:
                print(f"[EmailClient] Erro ao localizar mensagem original ID {entry_id[:10]}...: {e}")
                return False

            # Cria a resposta (Reply ou ReplyAll)
            if reply_all:
                reply_msg = original_msg.ReplyAll()
            else:
                reply_msg = original_msg.Reply()

            # Se o corpo veio com assinatura para o preview, removemos aqui pois o
            # reply_msg.HTMLBody JÁ contém a assinatura oficial do Outlook.
            clean_body = html_body
            if "<!-- SIGNATURE_START -->" in clean_body:
                import re
                clean_body = re.sub(r"<!-- SIGNATURE_START -->.*?<!-- SIGNATURE_END -->", "", clean_body, flags=re.DOTALL)
                clean_body = clean_body.strip()

            # Injeta o nosso corpo HTML no topo (o Outlook já colocou a assinatura e histórico abaixo)
            reply_msg.HTMLBody = clean_body + "<br><br>" + reply_msg.HTMLBody
            
            # Tenta forçar a conta correta se especificado
            if self.email_address:
                for account in outlook.Session.Accounts:
                    if account.SmtpAddress.lower() == self.email_address.lower():
                        reply_msg._oleobj_.Invoke(*(64209, 0, 8, 0, account)) # SendUsingAccount
                        break

            reply_msg.Send()
            print(f"[EmailClient] SUCCESS: Resposta (Thread) enviada via Outlook App para o ID {entry_id[:10]}...")
            return True
        except Exception as e:
            print(f"[EmailClient] ERROR (Reply Outlook): {e}")
            return False

    def scan_inbound_replies(self, folder: str = "INBOX", max_results: int = 10) -> List[Dict]:
        """
        Varre emails usando Outlook App ou IMAP.
        """
        if self.use_outlook_app:
            try:
                pythoncom.CoInitialize()
                outlook = self._get_outlook_instance()
                if not outlook: return []
                
                namespace = outlook.GetNamespace("MAPI")
                # Default to Inbox (6)
                target_folder = namespace.GetDefaultFolder(6)
                
                if folder and folder.lower() != "inbox":
                    try:
                        # Tenta buscar a pasta pelo nome
                        target_folder = target_folder.Parent.Folders.Item(folder)
                    except:
                        pass

                messages = target_folder.Items
                messages.Sort("[ReceivedTime]", True) # Mais novos primeiro
                
                replies = []
                count = 0
                for msg in messages:
                    if count >= max_results: break
                    if msg.UnRead:
                        replies.append({
                            "entryId": getattr(msg, 'EntryID', ""),
                            "conversationId": getattr(msg, 'ConversationID', ""),
                            "messageId": getattr(msg, 'MessageID', ""),
                            "sender": msg.SenderEmailAddress if hasattr(msg, 'SenderEmailAddress') else str(msg.Sender),
                            "to": msg.To,
                            "subject": msg.Subject,
                            "date": str(msg.ReceivedTime),
                            "body": getattr(msg, 'Body', '')[:1000]
                        })
                        count += 1
                
                print(f"[EmailClient] SUCCESS: Found {len(replies)} unread messages via Outlook App.")
                return replies
            except Exception as e:
                print(f"[EmailClient] ERROR (Outlook App Scan): {e}")
                return []
        else:
            # Fallback IMAP (exige senha)
            try:
                mail = imaplib.IMAP4_SSL(self.IMAP_SERVER)
                mail.login(self.email_address, self.password)
                mail.select(folder)
                status, messages = mail.search(None, 'UNSEEN')
                msg_ids = messages[0].split()
                latest_ids = msg_ids[-max_results:] if len(msg_ids) > max_results else msg_ids
                latest_ids.reverse()
                
                replies = []
                for msg_id in latest_ids:
                    status, data = mail.fetch(msg_id, '(RFC822)')
                    raw_email = data[0][1]
                    msg_obj = email.message_from_bytes(raw_email)
                    body = ""
                    if msg_obj.is_multipart():
                        for part in msg_obj.walk():
                            if part.get_content_type() in ["text/plain", "text/html"]:
                                body = part.get_payload(decode=True).decode(errors='ignore')
                                if part.get_content_type() == "text/html": break
                    else:
                        body = msg_obj.get_payload(decode=True).decode(errors='ignore')

                    replies.append({
                        "sender": msg_obj.get("From"),
                        "subject": msg_obj.get("Subject"),
                        "body": body,
                        "date": msg_obj.get("Date"),
                        "messageId": msg_obj.get("Message-ID")
                    })
                mail.logout()
                return replies
            except Exception as e:
                print(f"[EmailClient] ERROR (IMAP Scan): {e}")
                return []
    def _normalize_str(self, s: str) -> str:
        import unicodedata
        if not s: return ""
        return "".join(
            c for c in unicodedata.normalize('NFD', s.lower())
            if unicodedata.category(c) != 'Mn'
        ).strip()

    # Cache global para evitar lentidão do Outlook
    _contacts_cache = []
    _cache_timestamp = 0
    _is_syncing = False # Flag para indicar se está sincronizando no momento
    _CACHE_TTL = 300 # 5 minutos

    def _refresh_contacts_cache(self, force=False):
        """
        Varre o Outlook e atualiza a lista de contatos em memória.
        """
        current_time = time.time()
        if not force and EmailClient._contacts_cache and (current_time - EmailClient._cache_timestamp) < EmailClient._CACHE_TTL:
            return

        EmailClient._is_syncing = True # Inicia sincronização
        try:
            pythoncom.CoInitialize()
            outlook_app = self._get_outlook_instance()
            if not outlook_app: return
            
            outlook = outlook_app.GetNamespace("MAPI")
            new_cache = []
            
            # Lista prioritária de AddressLists
            print("[EmailClient] Atualizando cache de contatos do Outlook...")
            priority_names = ["global", "users", "usuarios", "contatos", "contacts"]
            ordered_lists = sorted(
                outlook.AddressLists, 
                key=lambda x: any(p in x.Name.lower() for p in priority_names), 
                reverse=True
            )

            for addr_list in ordered_lists:
                try:
                    count_total = addr_list.AddressEntries.Count
                    if count_total == 0: continue
                    
                    scan_limit = min(2000, count_total)
                    for i in range(1, scan_limit + 1):
                        try:
                            entry = addr_list.AddressEntries.Item(i)
                            name = getattr(entry, 'Name', "")
                            if not name: continue
                            
                            email_addr = ""
                            try:
                                if entry.Type == "SMTP": email_addr = entry.Address
                                else:
                                    u = entry.GetExchangeUser()
                                    email_addr = u.PrimarySmtpAddress if u else entry.Address
                            except: email_addr = getattr(entry, 'Address', "")

                            # Evitar duplicados por email
                            email_lower = (email_addr or "").lower()
                            if email_lower and any(c['email'].lower() == email_lower for c in new_cache):
                                continue

                            new_cache.append({
                                "name": name,
                                "email": email_addr or "Indisponível",
                                "norm_name": self._normalize_str(name),
                                "norm_email": self._normalize_str(email_addr),
                                "source": addr_list.Name
                            })
                        except: continue
                except: continue

            # --- ADICIONAL: ITENS ENVIADOS RECENTES NO CACHE ---
            try:
                sent_folder = outlook.GetDefaultFolder(5)
                sent_items = sent_folder.Items
                sent_items.Sort("[ReceivedTime]", True)
                max_scan = min(150, sent_items.Count)
                for i in range(1, max_scan + 1):
                    try:
                        msg = sent_items.Item(i)
                        items_rec = getattr(msg, 'Recipients', [])
                        for rec in items_rec:
                            r_name = getattr(rec, 'Name', "")
                            r_email = ""
                            try:
                                ae = rec.AddressEntry
                                if ae.Type == "SMTP": r_email = ae.Address
                                else:
                                    eu = ae.GetExchangeUser()
                                    r_email = eu.PrimarySmtpAddress if eu else ae.Address
                            except: r_email = getattr(rec, 'Address', "")
                            
                            if r_name and r_email:
                                if not any(c['email'].lower() == r_email.lower() for c in new_cache):
                                    new_cache.append({
                                        "name": r_name,
                                        "email": r_email,
                                        "norm_name": self._normalize_str(r_name),
                                        "norm_email": self._normalize_str(r_email),
                                        "source": "Recentes (Enviados)"
                                    })
                    except: continue
            except: pass
            
            EmailClient._contacts_cache = new_cache
            EmailClient._cache_timestamp = current_time
            print(f"[EmailClient] Cache atualizado com sucesso: {len(EmailClient._contacts_cache)} contatos.")
        except Exception as e:
            import traceback
            print(f"[EmailClient] Erro crítico ao atualizar cache: {e}")
            traceback.print_exc()
        finally:
            EmailClient._is_syncing = False # Finaliza sincronização

    def search_contacts(self, query: str, limit: int = 10) -> List[Dict]:
        """
        Busca contatos no catálogo de endereços do Outlook EXCLUSIVAMENTE via cache de memória.
        """
        if not self.use_outlook_app: return []

        # 1. Busca no Cache (Ultra-rápido, sem chamadas externas bloqueantes)
        results = []
        clean_query = self._normalize_str(query)
        clean_query_compact = clean_query.replace(" ", "")
        query_tokens = clean_query.split()
        
        print(f"[EmailClient] Buscando por '{query}' (norm: '{clean_query}'). Cache: {len(EmailClient._contacts_cache)} itens.")
        
        for c in EmailClient._contacts_cache:
            if len(results) >= limit: break
            
            # Cálculo de match:
            # Opção A: Substring direta (ex: "joaolu" em "joaoluccas@...")
            # Opção B: Todos os tokens presentes (ex: "joao lu" em "Joao Luccas")
            # Opção C: Match "colado" (ex: "joaolu" em "joao luccas" -> "joaoluccas")
            
            fullname_compact = c['norm_name'].replace(" ", "")
            email_compact = c['norm_email'].replace(" ", "")
            
            match_direct = clean_query in c['norm_name'] or clean_query in c['norm_email']
            match_tokens = len(query_tokens) > 1 and all(t in c['norm_name'] or t in c['norm_email'] for t in query_tokens)
            match_compact = clean_query_compact in fullname_compact or clean_query_compact in email_compact
            
            if match_direct or match_tokens or match_compact:
                print(f"[EmailClient] Conexão encontrada: {c['name']} ({c['email']})")
                results.append({
                    "name": c['name'],
                    "email": c['email'],
                    "type": "email",
                    "source": c['source']
                })
        return results

    def list_folders(self) -> List[str]:
        """
        Lista todas as pastas disponíveis na conta do Outlook.
        """
        if not self.use_outlook_app:
            return ["INBOX"]
        
        try:
            pythoncom.CoInitialize()
            outlook_app = self._get_outlook_instance()
            if not outlook_app: return ["INBOX"]
            
            outlook = outlook_app.GetNamespace("MAPI")
            folders = []
            for i in range(1, outlook.Folders.Count + 1):
                root = outlook.Folders.Item(i)
                for f in root.Folders:
                    folders.append(f"{root.Name} / {f.Name}")
            return folders
        except Exception as e:
            print(f"[EmailClient] ERROR (List Folders): {e}")
            return []

    def get_messages_from(self, folder_path: str = "Inbox", limit: int = 20, query: Optional[str] = None) -> List[Dict]:
        """
        Busca mensagens de pacotes ou de conversas.
        Se folder_path for 'Conversations', busca na Inbox e nos Enviados.
        """
        if self.use_outlook_app:
            try:
                pythoncom.CoInitialize()
                outlook_app = self._get_outlook_instance()
                if not outlook_app: return []
                
                outlook = outlook_app.GetNamespace("MAPI")
                
                # Tenta encontrar a conta JFERRES e mapear Inbox/Sent
                inbox = None
                sent = None
                try:
                    for store in outlook.Stores:
                        if "joao.moura" in store.DisplayName.lower():
                            root = store.GetRootFolder()
                            for f in root.Folders:
                                fname = f.Name.lower()
                                if fname == "caixa de entrada" or fname == "inbox":
                                    inbox = f
                                elif fname == "itens enviados" or fname == "sent items" or fname == "sent":
                                    sent = f
                            break
                except: pass
                
                # Fallbacks caso não encontre a Store específica
                if not inbox: inbox = outlook.GetDefaultFolder(6)
                if not sent: sent = outlook.GetDefaultFolder(5)

                if query:
                    query = self._normalize_str(query)
                
                folders_to_scan = []
                
                # Normalização de nomes
                fp_lower = folder_path.lower()
                is_inbox = fp_lower == "inbox" or fp_lower == "caixa de entrada"
                is_sent = fp_lower == "sent" or fp_lower == "itens enviados" or fp_lower == "sent items"
                is_conv = fp_lower == "conversations"

                if is_conv:
                    folders_to_scan = [inbox, sent]
                    # --- AUTO-DESCOBERTA DE PASTAS DE CLIENTES ---
                    if query and len(query) > 3:
                        def find_matching_folders(root_folder, q):
                            matches = []
                            try:
                                for f in root_folder.Folders:
                                    if q in f.Name.lower():
                                        matches.append(f)
                                    matches.extend(find_matching_folders(f, q))
                            except: pass
                            return matches
                        
                        # Extração de palavras-chave robusta (ex: matheus.muniz@knorr-bremse.com -> ['matheus', 'muniz', 'knorr', 'bremse'])
                        delimiters = [".", "@", "-", "_", " "]
                        temp_query = query.lower()
                        for d in delimiters:
                            temp_query = temp_query.replace(d, " ")
                        
                        skip_words = {"com", "br", "net", "org", "gov", "gmail", "outlook", "hotmail", "jferres", "linkb2b"}
                        kw = [k for k in temp_query.split() if len(k) > 3 and k not in skip_words]
                        
                        if kw:
                            # Tenta descobrir pastas usando as palavras-chave fortes
                            for word in kw:
                                print(f"[EmailClient] Buscando pastas relacionadas a '{word}'...")
                                client_folders = find_matching_folders(inbox.Parent, word)
                                for cf in client_folders:
                                    if cf not in folders_to_scan:
                                        print(f"[EmailClient] Auto-descoberta: Incluindo pasta '{cf.Name}'")
                                        folders_to_scan.append(cf)
                elif " / " in folder_path:
                    # Suporte para caminho direto: "Pastas / Subpasta"
                    try:
                        parts = [p.strip() for p in folder_path.split("/")]
                        curr = inbox.Parent
                        for p in parts:
                            curr = curr.Folders.Item(p)
                        folders_to_scan.append(curr)
                    except:
                        folders_to_scan.append(inbox)
                else:
                    target = inbox if is_inbox else (sent if is_sent else None)
                    if not target:
                        try: target = inbox.Folders.Item(folder_path)
                        except: target = inbox
                    folders_to_scan.append(target)

                all_items = []
                # Para evitar escaneamento lento, pegamos no máximo as 400 mais recentes de cada pasta
                scan_depth = 400 if query else limit
                
                for f_root in folders_to_scan:
                    folders_to_process = [f_root]
                    # Adiciona subpastas de 1º nível para não perder e-mails movidos por regras
                    try:
                        for sub in f_root.Folders:
                            folders_to_process.append(sub)
                    except: pass
                    
                    for f in folders_to_process:
                        try:
                            items = f.Items
                            items.Sort("[ReceivedTime]", True)
                            f_count = items.Count
                            # Pega as N mais recentes de cada (sub)pasta
                            for i in range(1, min(scan_depth, f_count) + 1):
                                try:
                                    all_items.append(items.Item(i))
                                except:
                                    pass
                        except: pass
                
                # Ordernar todos os itens localmente por tempo recebido (descendente)
                # O COM timestamp pode não suportar sorting do python diretamente, então convertemos para string caso falhe
                try:
                    all_items.sort(key=lambda x: str(getattr(x, 'ReceivedTime', '')), reverse=True)
                except:
                    pass
                
                results = []
                found = 0
                
                for msg in all_items:
                    if found >= limit: break
                    try:
                        if query:
                            s_name = self._normalize_str(getattr(msg, 'SenderName', ''))
                            s_email_raw = getattr(msg, 'SenderEmailAddress', '')
                            s_email = self._normalize_str(s_email_raw)
                            r_names_to = self._normalize_str(getattr(msg, 'To', ''))
                            
                            # Match simplificado
                            match = (query in s_name or query in s_email or query in r_names_to)
                            
                            # Se não deu match e o remetente parece ser Exchange (/o=...)
                            if not match and "/o=" in s_email_raw.lower():
                                try:
                                    sender = msg.Sender
                                    ae = sender.AddressEntry
                                    s_smtp = ""
                                    if ae.Type == "SMTP": s_smtp = ae.Address
                                    else:
                                        eu = ae.GetExchangeUser()
                                        s_smtp = eu.PrimarySmtpAddress if eu else ae.Address
                                    
                                    if query in self._normalize_str(s_smtp):
                                        match = True
                                except:
                                    pass
                            
                            # Match profundo: checar cada recipiente via SMTP se não deu match simples
                            if not match:
                                try:
                                    recipients = msg.Recipients
                                    for i in range(1, recipients.Count + 1):
                                        rec = recipients.Item(i)
                                        rec_name = self._normalize_str(getattr(rec, 'Name', ''))
                                        rec_addr = ""
                                        try:
                                            ae = rec.AddressEntry
                                            if ae.Type == "SMTP": rec_addr = ae.Address
                                            else:
                                                eu = ae.GetExchangeUser()
                                                rec_addr = eu.PrimarySmtpAddress if eu else ae.Address
                                        except:
                                            rec_addr = getattr(rec, 'Address', '')
                                        
                                        rec_addr_norm = self._normalize_str(rec_addr)
                                        if query in rec_name or query in rec_addr_norm:
                                            match = True
                                            break
                                except:
                                    pass

                            if not match:
                                continue

                        # Tenta obter o SMTP real para o display da IA
                        display_sender = s_email_raw
                        if "/o=" in s_email_raw.lower():
                            try:
                                ae = msg.Sender.AddressEntry
                                if ae.Type == "SMTP": display_sender = ae.Address
                                else:
                                    eu = ae.GetExchangeUser()
                                    display_sender = eu.PrimarySmtpAddress if eu else ae.Address
                            except: pass

                        # Resolve todos os destinatários para SMTP REAL
                        resolved_to = []
                        try:
                            recipients = msg.Recipients
                            for i in range(1, recipients.Count + 1):
                                r = recipients.Item(i)
                                r_smtp = ""
                                try:
                                    ae = r.AddressEntry
                                    if ae.Type == "SMTP": r_smtp = ae.Address
                                    else:
                                        eu = ae.GetExchangeUser()
                                        r_smtp = eu.PrimarySmtpAddress if eu else ae.Address
                                except:
                                    r_smtp = getattr(r, 'Address', '')
                                
                                if r_smtp: resolved_to.append(r_smtp)
                                else: resolved_to.append(r.Name) # Fallback para o nome
                        except:
                            resolved_to = [getattr(msg, 'To', 'Unknown')]

                        results.append({
                            "entryId": getattr(msg, 'EntryID', ""),
                            "conversationId": getattr(msg, 'ConversationID', ""),
                            "messageId": getattr(msg, 'MessageID', ""),
                            "sender": display_sender,
                            "to": "; ".join(resolved_to),
                            "subject": getattr(msg, 'Subject', ''),
                            "date": str(getattr(msg, 'ReceivedTime', '')),
                            "body": getattr(msg, 'Body', '')[:1000]
                        })
                        found += 1
                    except Exception as e:
                        pass
                return results
            except Exception as e:
                print(f"[EmailClient] ERROR (Get Messages from {folder_path}): {e}")
        return []

    def get_default_signature(self) -> str:
        """
        Cria um rascunho dummy apenas para capturar a assinatura padrão do usuário.
        """
        if not self.use_outlook_app: return ""
        try:
            pythoncom.CoInitialize()
            outlook = self._get_outlook_instance()
            if not outlook: return ""
            dummy = outlook.CreateItem(0)
            
            # O Outlook precisa ser exibido ou "inspecionado" para inserir a assinatura
            dummy.Display()
            
            # Pequeno delay humano para o Outlook renderizar a assinatura no HTMLBody
            import time
            time.sleep(0.6)
            
            sig_html = dummy.HTMLBody
            
            # 1. Extrair apenas o conteúdo interno do <body> para evitar nesting de tags <html> no preview
            import re
            body_match = re.search(r"<body[^>]*>(.*?)</body>", sig_html, re.IGNORECASE | re.DOTALL)
            if body_match:
                sig_html = body_match.group(1)
            
            # 2. Limpeza: Remover parágrafos vazios que o Outlook insere no topo do rascunho
            sig_html = re.sub(r"^(\s*<p[^>]*>(&nbsp;|\s)*</p>\s*)*", "", sig_html, flags=re.IGNORECASE)
            
            # 3. Mágica de Imagens: Converter caminhos locais (file:///) para Base64
            # Isso permite que as imagens da assinatura apareçam no preview do navegador
            def _base64_replacer(match):
                full_tag = match.group(0)
                quote = match.group(1)
                img_path = match.group(2)
                
                if img_path.startswith("file:///"):
                    local_path = img_path.replace("file:///", "").replace("/", "\\")
                    # Em alguns casos o Outlook usa escapes de URL
                    import urllib.parse
                    local_path = urllib.parse.unquote(local_path)
                    
                    if os.path.exists(local_path):
                        try:
                            import base64
                            with open(local_path, "rb") as f:
                                b64 = base64.b64encode(f.read()).decode()
                            ext = local_path.split(".")[-1].lower()
                            mime = f"image/{ext}" if ext in ["png", "jpg", "jpeg", "gif"] else "image/png"
                            return f'src="data:{mime};base64,{b64}"'
                        except: pass
                return full_tag

            sig_html = re.sub(r'src=(["\'])(.*?)\1', _base64_replacer, sig_html)

            dummy.Close(1) # clDiscard (Não salvar rascunho)
            return sig_html
        except Exception as e:
            print(f"[EmailClient] Erro ao capturar assinatura para preview: {e}")
            return ""

    def mark_as_read(self, entry_id: str):
        """
        Marca um email específico como lido no Outlook.
        """
        if self.use_outlook_app:
            try:
                pythoncom.CoInitialize()
                outlook_app = self._get_outlook_instance()
                if not outlook_app: return False
                
                outlook = outlook_app.GetNamespace("MAPI")
                item = outlook.GetItemFromID(entry_id)
                item.UnRead = False
                item.Save()
                return True
            except Exception as e:
                print(f"[EmailClient] ERROR (Mark as Read): {e}")
        return False
