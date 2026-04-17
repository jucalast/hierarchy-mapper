import os
import sys
from dotenv import load_dotenv

# Carregar env da raiz
load_dotenv("../../.env")

# Adicionar o root ao path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from services.communication.email_client import EmailClient

def test_connection():
    email = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASSWORD")
    
    if not email or not password or password == "SUA_SENHA_AQUI_OU_APP_PASSWORD":
        print("❌ Erro: EMAIL_USER ou EMAIL_PASSWORD não configurados no .env")
        return

    print(f"🔄 Testando conexão para {email}...")
    client = EmailClient(email, password)
    
    # Testar SMTP
    print("📡 Testando SMTP (Envio)...")
    try:
        import smtplib
        server = smtplib.SMTP(client.SMTP_SERVER, client.SMTP_PORT)
        server.starttls()
        server.login(email, password)
        server.quit()
        print("✅ SMTP: Conexão e Login bem-sucedidos!")
    except Exception as e:
        print(f"❌ SMTP: Falha - {e}")

    # Testar IMAP
    print("📡 Testando IMAP (Recebimento)...")
    try:
        import imaplib
        mail = imaplib.IMAP4_SSL(client.IMAP_SERVER)
        mail.login(email, password)
        mail.logout()
        print("✅ IMAP: Conexão e Login bem-sucedidos!")
    except Exception as e:
        print(f"❌ IMAP: Falha - {e}")

if __name__ == "__main__":
    test_connection()
