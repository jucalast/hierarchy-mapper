"""
modules.communication.service.email.client
==========================================
Cliente de e-mail com suporte a Outlook (pywin32) e fallback SMTP/IMAP.

Grupos de responsabilidade na classe EmailClient:
    COM setup      → _get_outlook_instance, _handle_com_error
    Envio          → send_outbound_email, reply_to_email
    Leitura        → scan_inbound_replies, get_messages_from, mark_as_read
    Contatos       → _refresh_contacts_cache, search_contacts, list_folders
    Utilitários    → _normalize_str, get_default_signature

Estado de classe (cache compartilhado entre instâncias):
    _contacts_cache    → lista de contatos do Outlook em memória (TTL 5 min)
    _signature_cache   → assinatura HTML padrão do usuário
    _cache_timestamp   → timestamp da última atualização do cache de contatos
"""
import os
import time
import random
from typing import List, Dict, Optional
from core.observability.logging_config import get_logger

log = get_logger(__name__)

import re
import unicodedata
import smtplib
import imaplib
import mimetypes
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

# Tenta importar win32com para a "mágica" do Windows/Outlook
try:
    import win32com.client
    import pythoncom
    HAS_PYWIN32 = True
except ImportError:
    HAS_PYWIN32 = False

class EmailClient:
    """
    Cliente de email que utiliza integração direta com o Outlook (via pywin32) no Windows,
    ou SMTP/IMAP tradicional como fallback ou em outros sistemas.
    """

    SMTP_SERVER = "smtp.office365.com"
    SMTP_PORT = 587
    IMAP_SERVER = "outlook.office365.com"
    IMAP_PORT = 993

    # Servidores Office 365 que não aceitam mais autenticação básica (removida out/2022)
    _MODERN_AUTH_SERVERS = {"outlook.office365.com", "outlook.office.com"}
    _imap_legacy_warned: bool = False  # emite aviso apenas uma vez por processo
    
    def __init__(self, email_address=None, password=None, use_outlook_app=True):
        from core.config import settings
        self.email_address = email_address or settings.EMAIL_USER
        self.password = password or settings.EMAIL_PASSWORD
        self.use_outlook_app = use_outlook_app and HAS_PYWIN32
        
        if self.use_outlook_app:
            log.info("email.outlook.initialized")
            # Tenta inicializar uma vez para garantir que o COM está ok
            try:
                pythoncom.CoInitialize()
                self._get_outlook_instance()
            except:
                pass
        elif not self.password:
            log.warning("email.smtp.password_missing")

    def _get_outlook_instance(self, force_new=False):
        """
        Tenta pegar uma instância já aberta do Outlook ou cria uma nova de forma silenciosa.
        """
        if not HAS_PYWIN32: return None
        
        try:
            outlook = None
            if not force_new:
                try:
                    outlook = win32com.client.GetActiveObject("Outlook.Application")
                except:
                    pass
            
            if not outlook:
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
            log.error("email.outlook.get_instance_failed", error=str(e))
            return None

    def _handle_com_error(self, e, context_msg):
        """
        Trata erros comuns de COM, como o servidor RPC indisponível.
        Retorna True se deve tentar novamente.
        """
        err_msg = str(e)
        # Erro RPC (-2147023174 ou 0x800706BA)
        if "-2147023174" in err_msg or "0x800706BA" in err_msg or "RPC" in err_msg:
            log.warning("email.outlook.rpc_error", context=context_msg)
            return True
        log.error("email.outlook.error", context=context_msg, error=e)
        return False

    def send_outbound_email(self, to_email: str, subject: str, html_body: str, tracking_id: Optional[str] = None, request_read_receipt: bool = False, attachment_paths: Optional[List[str]] = None):
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
            for attempt in range(2):
                try:
                    pythoncom.CoInitialize()
                    outlook = self._get_outlook_instance(force_new=(attempt > 0))
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
                        # Tenta usar cache para evitar Display() que é LENTO e bloqueante
                        if not EmailClient._signature_cache:
                            log.debug("email.outlook.signature_fetch")
                            EmailClient._signature_cache = self.get_default_signature()
                        
                        if EmailClient._signature_cache:
                            mail.HTMLBody = final_body + "<br><br>" + EmailClient._signature_cache
                        else:
                            # 🛑 SEGURANÇA: Não usamos .Display() em background para evitar popups.
                            # Se não tem assinatura em cache, envia apenas o corpo.
                            log.warning("email.outlook.signature_not_found")
                            mail.HTMLBody = final_body
                    
                    if request_read_receipt:
                        mail.ReadReceiptRequested = True
                    
                    # Selecionar conta correta
                    if self.email_address:
                        for account in outlook.Session.Accounts:
                            if account.SmtpAddress.lower() == self.email_address.lower():
                                mail._oleobj_.Invoke(*(64209, 0, 8, 0, account)) # SendUsingAccount
                                break
                    
                    # Anexos (aceita lista de caminhos absolutos)
                    if attachment_paths:
                        for ap in attachment_paths:
                            if ap and os.path.exists(ap):
                                try:
                                    mail.Attachments.Add(ap)
                                    log.info("email.outlook.attachment_added", path=ap)
                                except Exception as ae:
                                    log.warning("email.outlook.attachment_failed", path=ap, error=ae)

                    mail.Send()
                    log.info("email.sent.success", provider="outlook", to=to_email)
                    return True
                except Exception as e:
                    if attempt == 0 and self._handle_com_error(e, "Outlook App Send"):
                        continue
                    return False
        else:
            # Fallback SMTP
            if not self.password:
                log.error("email.smtp.password_missing_for_send")
                return False
            msg = MIMEMultipart()
            msg['From'] = self.email_address
            msg['To'] = to_email
            msg['Subject'] = subject
            msg.attach(MIMEText(final_body, 'html'))

            # Anexos SMTP
            if attachment_paths:
                for ap in attachment_paths:
                    if ap and os.path.exists(ap):
                        try:
                            mime_type, _ = mimetypes.guess_type(ap)
                            main_type, sub_type = (mime_type.split('/') if mime_type else ('application', 'octet-stream'))
                            with open(ap, 'rb') as f:
                                part = MIMEBase(main_type, sub_type)
                                part.set_payload(f.read())
                            encoders.encode_base64(part)
                            part.add_header('Content-Disposition', 'attachment', filename=os.path.basename(ap))
                            msg.attach(part)
                            log.info("email.smtp.attachment_added", path=ap)
                        except Exception as ae:
                            log.warning("email.smtp.attachment_failed", path=ap, error=ae)

            try:
                server = smtplib.SMTP(self.SMTP_SERVER, self.SMTP_PORT)
                server.starttls()
                server.login(self.email_address, self.password)
                server.send_message(msg)
                server.quit()
                log.info("email.sent.success", provider="smtp", to=to_email)
                return True
            except Exception as e:
                log.error("email.sent.error", provider="smtp", error=e)
                return False

    def reply_to_email(self, entry_id: str, html_body: str, reply_all: bool = True, attachment_paths: Optional[List[str]] = None):
        """
        Responde a um e-mail específico mantendo a Thread (In-Reply-To).
        """
        if not self.use_outlook_app:
            log.warning("email.reply.outlook_only")
            return False

        for attempt in range(2):
            try:
                pythoncom.CoInitialize()
                outlook = self._get_outlook_instance(force_new=(attempt > 0))
                if not outlook: return False

                # Localiza a mensagem original
                try:
                    namespace = outlook.GetNamespace("MAPI")
                    original_msg = namespace.GetItemFromID(entry_id)
                except Exception as e:
                    log.error("email.outlook.item_not_found", entry_id=entry_id[:10], error=e)
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

                # Anexos
                if attachment_paths:
                    for ap in attachment_paths:
                        if ap and os.path.exists(ap):
                            try:
                                reply_msg.Attachments.Add(ap)
                            except Exception as ae:
                                log.warning("email.outlook.reply_attachment_failed", path=ap, error=ae)

                reply_msg.Send()
                log.info("email.reply.success", entry_id=entry_id[:10])
                return True
            except Exception as e:
                if attempt == 0 and self._handle_com_error(e, "Reply Outlook"):
                    continue
                return False

    def scan_inbound_replies(self, folder: str = "INBOX", max_results: int = 10) -> List[Dict]:
        """
        Varre emails usando Outlook App ou IMAP.
        """
        if self.use_outlook_app:
            for attempt in range(2):
                try:
                    pythoncom.CoInitialize()
                    outlook_app = self._get_outlook_instance(force_new=(attempt > 0))
                    if not outlook_app: return []
                    
                    namespace = outlook_app.GetNamespace("MAPI")
                    # Default to Inbox (6)
                    target_folder = namespace.GetDefaultFolder(6)
                    
                    if folder and folder.lower() != "inbox":
                        try:
                            # Tenta buscar a pasta pelo nome
                            target_folder = target_folder.Parent.Folders.Item(folder)
                        except:
                            pass

                    messages = target_folder.Items
                    try:
                        messages.Sort("[ReceivedTime]", True) # Mais novos primeiro
                    except:
                        try: messages.Sort("[CreationTime]", True)
                        except: pass
                    
                    replies = []
                    count = 0
                    for msg in messages:
                        if count >= max_results: break
                        try:
                            if getattr(msg, 'UnRead', False):
                                replies.append({
                                    "entryId": getattr(msg, 'EntryID', ""),
                                    "conversationId": getattr(msg, 'ConversationID', ""),
                                    "messageId": getattr(msg, 'MessageID', ""),
                                    "sender": msg.SenderEmailAddress if hasattr(msg, 'SenderEmailAddress') else str(getattr(msg, 'Sender', 'Unknown')),
                                    "to": getattr(msg, 'To', ""),
                                    "subject": getattr(msg, 'Subject', ""),
                                    "date": str(getattr(msg, 'ReceivedTime', '')),
                                    "body": getattr(msg, 'Body', '')[:1000]
                                })
                                count += 1
                        except: continue
                    
                    log.debug("email.scan.success", count=len(replies))
                    return replies
                except Exception as e:
                    if attempt == 0 and self._handle_com_error(e, "Outlook App Scan"):
                        continue
                    return []
        else:
            # Fallback IMAP (exige senha)
            if not self.password:
                return []
            # Office 365 removeu autenticação básica do IMAP em out/2022.
            # Tentativas retornam "AUTHENTICATE failed" — aborta antes de conectar.
            from core.config import settings
            is_modern_auth_server = self.IMAP_SERVER in self._MODERN_AUTH_SERVERS
            if is_modern_auth_server and not getattr(settings.email, "imap_legacy_auth", False):
                if not EmailClient._imap_legacy_warned:
                    log.warning(
                        "email.imap.skipped.modern_auth_required",
                        server=self.IMAP_SERVER,
                        hint="Office 365 não aceita mais Basic Auth para IMAP. "
                             "Configure EMAIL_SCAN_IMAP_LEGACY_AUTH=true se o tenant ainda tiver legacy auth, "
                             "ou implemente OAuth2/Graph API.",
                    )
                    EmailClient._imap_legacy_warned = True
                return []
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
                log.error("email.imap.scan_error", error=e)
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
    _signature_cache = None # Cache para a assinatura HTML

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
            log.debug("email.outlook.contacts_refresh")
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
                try:
                    sent_items.Sort("[ReceivedTime]", True)
                except:
                    try: sent_items.Sort("[CreationTime]", True)
                    except: pass
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
            log.info("email.outlook.cache_updated", count=len(EmailClient._contacts_cache))
        except Exception as e:
            import traceback
            log.error("email.outlook.cache_error", error=e)
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
        
        log.debug("email.contacts.search", query=query, cache_size=len(EmailClient._contacts_cache))
        
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
                log.debug("email.contacts.match", name=c['name'], email=c['email'])
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
            log.error("email.outlook.list_folders_error", error=e)
            return []

    def get_messages_from(self, folder_path: str = "Inbox", limit: int = 20, query: Optional[str] = None) -> List[Dict]:
        """
        Busca mensagens de pacotes ou de conversas.
        Se folder_path for 'Conversations', busca na Inbox e nos Enviados.
        """
        if self.use_outlook_app:
            for attempt in range(2):
                try:
                    pythoncom.CoInitialize()
                    outlook_app = self._get_outlook_instance(force_new=(attempt > 0))
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

                    def get_all_folders_recursive(root):
                        all_f = []
                        try:
                            # Filtro: Apenas pastas que podem conter emails (olMailItem=0, olPostItem=6)
                            # Se for o root (Store), ele pode não ter DefaultItemType, então incluímos.
                            if not hasattr(root, 'DefaultItemType') or root.DefaultItemType in [0, 6]:
                                all_f.append(root)
                        except:
                            all_f.append(root)
                            
                        try:
                            for sub in root.Folders:
                                all_f.extend(get_all_folders_recursive(sub))
                        except: pass
                        return all_f

                    if is_conv:
                        # Busca em TODAS as pastas da conta principal
                        if inbox:
                            log.debug("email.outlook.recursive_scan", query=query)
                            folders_to_scan = get_all_folders_recursive(inbox.Parent)
                        else:
                            folders_to_scan = [inbox, sent]
                    elif " / " in folder_path:                        # Suporte para caminho direto: "Pastas / Subpasta"
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
                    
                    # OTIMIZAÇÃO: Filtro nativo do Outlook (Restrict) em vez de loop manual
                    # Isso reduz drasticamente o tempo de resposta e evita ReadTimeout
                    filter_str = ""
                    if query:
                        q_clean = query.replace("'", "''") # Escape single quotes
                        
                        # Usamos MAPI Property Tags para maior compatibilidade no Restrict
                        # 0x0065001F = SenderEmailAddress, 0x0E04001F = DisplayTo, 0x0E03001F = DisplayCc, 0x0037001F = Subject, 0x1000001F = Body
                        if "@" in q_clean:
                            filter_str = (
                                f"@SQL=(\"http://schemas.microsoft.com/mapi/proptag/0x0065001F\" LIKE '%{q_clean}%' "
                                f"OR \"http://schemas.microsoft.com/mapi/proptag/0x0E04001F\" LIKE '%{q_clean}%' "
                                f"OR \"http://schemas.microsoft.com/mapi/proptag/0x0E03001F\" LIKE '%{q_clean}%' "
                                f"OR \"http://schemas.microsoft.com/mapi/proptag/0x1000001F\" LIKE '%{q_clean}%' "
                                f"OR \"http://schemas.microsoft.com/mapi/proptag/0x0E02001F\" LIKE '%{q_clean}%')" # BCC
                            )
                        else:
                            filter_str = (
                                f"@SQL=(\"http://schemas.microsoft.com/mapi/proptag/0x0042001F\" LIKE '%{q_clean}%' " # SenderName
                                f"OR \"http://schemas.microsoft.com/mapi/proptag/0x0E04001F\" LIKE '%{q_clean}%' "
                                f"OR \"http://schemas.microsoft.com/mapi/proptag/0x0E03001F\" LIKE '%{q_clean}%' "
                                f"OR \"http://schemas.microsoft.com/mapi/proptag/0x0037001F\" LIKE '%{q_clean}%')"
                            )
                    
                    # Evitar duplicidade se folders_to_scan já for recursivo
                    unique_folders = folders_to_scan
                    if not is_conv:
                        # Para pastas únicas, incluímos os subdiretórios imediatos por padrão
                        unique_folders = []
                        for f_root in folders_to_scan:
                            unique_folders.append(f_root)
                            try:
                                for sub in f_root.Folders:
                                    unique_folders.append(sub)
                            except: pass

                    for f in unique_folders:
                        try:
                            # Pula pastas que sabemos que não tem ReceivedTime (Contatos=2, Calendário=1, etc)
                            if hasattr(f, 'DefaultItemType') and f.DefaultItemType not in [0, 6]:
                                continue
                                
                            items = f.Items
                            if filter_str:
                                # Filtro DASL é muito mais rápido que loop
                                try:
                                    items = items.Restrict(filter_str)
                                except Exception as e:
                                    log.debug("email.outlook.restrict_failed", error=e)
                                    # Fallback para busca mais simples
                                    try:
                                        simple_filter = f"@SQL=(\"urn:schemas:httpmail:textdescription\" LIKE '%{q_clean}%')"
                                        items = items.Restrict(simple_filter)
                                    except:
                                        pass
                            
                            try:
                                items.Sort("[ReceivedTime]", True)
                            except:
                                try: items.Sort("[CreationTime]", True)
                                except: pass
                            
                            # Pega apenas os necessários do topo filtrado
                            f_count = items.Count
                            for i in range(1, min(limit, f_count) + 1):
                                try:
                                    all_items.append(items.Item(i))
                                except: pass
                        except Exception as fe:
                            # Ignora erro silenciosamente se for apenas falta de propriedade
                            if "ReceivedTime" not in str(fe):
                                log.warning("email.outlook.folder_filter_error", folder=getattr(f, 'Name', 'Unknown'), error=str(fe))
                    
                    # Ordernar todos os itens localmente por tempo recebido (descendente)
                    try:
                        all_items.sort(key=lambda x: str(getattr(x, 'ReceivedTime', '')), reverse=True)
                    except: pass
                    
                    results = []
                    found = 0
                    
                    # Agora o loop é apenas sobre os resultados já pré-filtrados pelo Outlook
                    # Faremos também um filtro local para garantir a precisão, já que o Restrict pode falhar ou ser permissivo.
                    q_lower = query.lower() if query else ""
                    
                    for msg in all_items:
                        if found >= limit: break
                        try:
                            # Tenta obter o SMTP real para o display da IA
                            s_email_raw = getattr(msg, 'SenderEmailAddress', '')
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
                                    else: resolved_to.append(r.Name)
                            except:
                                resolved_to = [getattr(msg, 'To', 'Unknown')]

                            to_str = "; ".join(resolved_to)
                            subj_str = getattr(msg, 'Subject', '')
                            body_str = getattr(msg, 'Body', '')
                            
                            # Filtro Local de Segurança:
                            if q_lower:
                                # Debug logging
                                match_sender = q_lower in display_sender.lower()
                                match_to = q_lower in to_str.lower()
                                match_subj = q_lower in subj_str.lower()
                                match_body = q_lower in body_str.lower()
                                
                                if not (match_sender or match_to or match_subj or match_body):
                                    continue # Pula se não bateu
                                    
                            results.append({
                                "entryId": getattr(msg, 'EntryID', ""),
                                "conversationId": getattr(msg, 'ConversationID', ""),
                                "messageId": getattr(msg, 'MessageID', ""),
                                "sender": display_sender,
                                "to": to_str,
                                "subject": subj_str,
                                "date": str(getattr(msg, 'ReceivedTime', '')),
                                "body": body_str[:1000]
                            })
                            found += 1
                        except Exception as e:
                            pass
                    return results
                except Exception as e:
                    if attempt == 0 and self._handle_com_error(e, f"Get Messages from {folder_path}"):
                        continue
                    log.error("email.outlook.get_messages_error", folder=folder_path, error=e)
        return []

    def get_default_signature(self) -> str:
        """
        Cria um rascunho dummy apenas para capturar a assinatura padrão do usuário.
        """
        if not self.use_outlook_app: return ""
        
        # Tenta retornar do cache primeiro
        if EmailClient._signature_cache:
            return EmailClient._signature_cache

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
            
            # Salva no cache
            EmailClient._signature_cache = sig_html
            
            return sig_html
        except Exception as e:
            log.warning("email.outlook.signature_capture_failed", error=str(e))
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
                log.error("email.outlook.mark_as_read_failed", error=str(e))
        return False
