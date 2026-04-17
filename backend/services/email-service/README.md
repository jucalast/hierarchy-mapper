# Email Discovery Service (Python)

Este serviço é responsável por gerenciar comunicações via E-mail utilizando protocolos tradicionais (SMTP/IMAP), evitando a complexidade de permissões do Azure AD/Microsoft Graph.

## Configuração

1. Certifique-se de que o arquivo `.env` na raiz do backend possui as seguintes chaves:
   ```env
   EMAIL_USER=joao.moura@jferres.com.br
   EMAIL_PASSWORD=SUA_SENHA_AQUI
   EMAIL_PORT=8002
   ```
2. Caso use Office 365, você deve habilitar o **Authenticated SMTP** nas configurações do usuário no Admin Center do Microsoft 365 e, se tiver MFA habilitado, gerar uma **App Password**.

## Instalação e Execução

```bash
cd backend/services/email-service
pip install -r requirements.txt
python main.py
```

## Endpoints

- `POST /api/email/send`: Envia um email.
- `GET /api/email/replies`: Busca emails não lidos via IMAP.
- `GET /api/email/health`: Verifica o status do serviço.
