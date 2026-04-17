import os
import sys
from dotenv import load_dotenv

# Carregar env da raiz
load_dotenv("../../.env")

# Adicionar o root ao path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from services.communication.email_client import EmailClient

def send_test():
    email = os.getenv("EMAIL_USER", "joao.moura@jferres.com.br")
    password = os.getenv("EMAIL_PASSWORD")
    
    # Se estivermos no Windows e o Outlook estiver instalado, a senha não é obrigatória
    print(f"[SendTest] Iniciando teste para {email}...")
    
    # Forçamos o uso do Outlook App por ser o "método mágico"
    client = EmailClient(email, password, use_outlook_app=True)
    
    dest = "joaoluccas637@gmail.com"
    print(f"[SendTest] Enviando via Outlook Desktop para {dest}...")
    
    success = client.send_outbound_email(
        to_email=dest,
        subject="Teste Magico: Python + Outlook Desktop",
        html_body="""
        <h1>Funciona!!</h1>
        <p>Este e-mail foi enviado usando o seu <b>Outlook Desktop</b> instalado no Windows.</p>
        <p>Sem senhas no código, sem permissões de Azure, sem SMTP bloqueado.</p>
        """
    )
    
    if success:
        print("SUCCESS: Email enviado via Outlook Desktop!")
    else:
        print("ERROR: Houve um erro ao tentar usar o Outlook Desktop. Certifique-se de que o Outlook está aberto e logado.")

if __name__ == "__main__":
    send_test()
