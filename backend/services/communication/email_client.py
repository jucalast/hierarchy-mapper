import smtplib
import imaplib
import email
import time
import random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate
import os

class EmailClient:
    def __init__(self, smtp_server="smtp.office365.com", smtp_port=587, 
                 imap_server="outlook.office365.com", imap_port=993,
                 email_address=None, email_password=None):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.imap_server = imap_server
        self.imap_port = imap_port
        self.email_address = email_address or os.getenv("EMAIL_SENDER_USER")
        self.email_password = email_password or os.getenv("EMAIL_SENDER_PASS")

    def _get_smtp_connection(self):
        try:
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.ehlo()
            server.starttls()
            server.login(self.email_address, self.email_password)
            return server
        except Exception as e:
            print(f"[EmailClient] Erro de Autenticação SMTP: {e}")
            # Idealmente, notificar via WhatsApp/Log estruturado
            raise e

    def _get_imap_connection(self):
        try:
            mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            mail.login(self.email_address, self.email_password)
            return mail
        except Exception as e:
            print(f"[EmailClient] Erro de Autenticação IMAP: {e}")
            raise e

    def send_outbound_email(self, to_email: str, subject: str, html_body: str, tracking_id: str):
        """
        Envia e-mail injetando um pixel invisível para rastrear aberturas
        com atraso aleatório para simular comportamento humano e não queimar o domínio.
        """
        # Delay humano (evitar block de spam)
        # Em produção, um delay muito grande numa task síncrona pode travar, 
        # mas como rodará em worker background (celery/arq), está seguro.
        # Ajustado para um valor MVP (2 a 5 segundos), mas sugerido 2-8 min.
        time.sleep(random.uniform(2.0, 5.0))

        msg = MIMEMultipart('alternative')
        msg['From'] = self.email_address
        msg['To'] = to_email
        msg['Subject'] = subject
        msg['Date'] = formatdate(localtime=True)

        # Injetar Pixel de Rastreio
        tracking_url = f"{os.getenv('API_BASE_URL', 'http://127.0.0.1:8000')}/api/v1/communication/track?id={tracking_id}"
        pixel_html = f'<img src="{tracking_url}" width="1" height="1" style="display:none;" />'
        
        final_body = html_body + pixel_html
        msg.attach(MIMEText(final_body, 'html'))

        try:
            server = self._get_smtp_connection()
            server.sendmail(self.email_address, to_email, msg.as_string())
            server.quit()
            print(f"[EmailClient] E-mail enviado com sucesso para {to_email}")
            return True
        except Exception as e:
            print(f"[EmailClient] ❌ Falha ao enviar e-mail para {to_email}: {e}")
            return False

    def scan_inbound_replies(self, folder="Leads"):
        """
        Varre apenas a subpasta designada para respostas comerciais, 
        evitando gargalo de processamento da Inbox inteira.
        """
        try:
            mail = self._get_imap_connection()
            
            # Tentar selecionar a pasta específica ('Leads' ou similar criada via regra)
            status, messages = mail.select(f'"{folder}"')
            if status != 'OK':
                print(f"[EmailClient] Pasta '{folder}' não encontrada. Verifique as regras do Outlook.")
                mail.select('inbox') # Fallback
            
            # Buscar e-mails não lidos
            status, response = mail.search(None, 'UNSEEN')
            if status != 'OK':
                return []
            
            unread_ids = response[0].split()
            replies = []
            
            for e_id in unread_ids:
                status, msg_data = mail.fetch(e_id, '(RFC822)')
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        subject = email.header.decode_header(msg['Subject'])[0][0]
                        if isinstance(subject, bytes):
                            subject = subject.decode()
                        
                        sender = msg.get('From')
                        body = ""
                        
                        if msg.is_multipart():
                            for part in msg.walk():
                                content_type = part.get_content_type()
                                content_disposition = str(part.get("Content-Disposition"))
                                
                                if type == "text/plain" and "attachment" not in content_disposition:
                                    body = part.get_payload(decode=True).decode()
                                    break
                        else:
                            body = msg.get_payload(decode=True).decode()
                            
                        replies.append({
                            "sender": sender,
                            "subject": subject,
                            "body": body
                        })
            
            mail.close()
            mail.logout()
            return replies
            
        except Exception as e:
            print(f"[EmailClient] ❌ Erro ao escanear respostas: {e}")
            return []
