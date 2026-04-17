# 🚀 Migração do Email System para OAuth2 + Microsoft Graph API

## Status: ✅ 95% CONCLUÍDO

### ✅ O Que Foi Realizado

#### 1. **Refatoração do Backend**
- ✅ Criado novo `EmailClient` baseado em **Microsoft Graph API + OAuth2**
- ✅ Removido autenticação BasicAuth (IMAP/SMTP) que estava bloqueada no tenant corporativo
- ✅ Implementado MSAL (Microsoft Authentication Library) para geração de tokens OAuth
- ✅ Atualizado `backend/.env` com credenciais Azure:
  - `AZURE_TENANT_ID`: e810eb4d-9b69-4af6-853c-4b50e0d7573f
  - `AZURE_CLIENT_ID`: ebdcc6e5-615f-4785-af87-dc302bfe3087
  - `AZURE_CLIENT_SECRET`: SUA_SECRET_AQUI_NO_ENV_APENAS

#### 2. **Recursos Implementados**
- ✅ Autenticação via MSAL (Client Credentials Flow)
- ✅ Método `send_outbound_email()`: Envia emails com rastreamento de abertura
- ✅ Método `scan_inbound_replies()`: Busca emails não lidos na inbox
- ✅ Método `_get_folder_id()`: Suporta pastas customizadas (ex: "Leads")

#### 3. **Testes**
- ✅ OAuth2 Authentication: **SUCESSO**
- ⏳ Email Fetch: Requer permissões Graph API (próximo passo)
- ⏳ Email Send: Requer permissões Graph API (próximo passo)

---

## ⏳ PRÓXIMOS PASSOS: Configurar Permissões no Azure

### Por que isso é necessário?
O App Registration foi criado, mas sem as permissões Graph API necessárias. Isso é por design de segurança - cada app deve ter permissões explícitas aprovadas pelo admin do tenant.

### ✍️ Como Adicionar Permissões (Azure Portal)

**Passo 1:** Acesse o Entra Admin Center
- URL: https://entra.microsoft.com/
- Faça login com sua conta corporativa JFerres

**Passo 2:** Navegue até App Registration
1. Left sidebar → "Applications" → "App registrations"
2. Procure por "LinkB2B Email Sync" (ou clique na aba "All applications")
3. Clique no App para abrir seus detalhes

**Passo 3:** Adicionar Permissões API
1. No sidebar esquerdo, clique em **"API permissions"**
2. Clique no botão azul **"+ Add a permission"**
3. Selecione **"Microsoft Graph"**
4. Escolha **"Application permissions"** (não delegated)

**Passo 4:** Buscar e Selecionar Permissões
Na caixa de busca, procure por estas permissões:
- **Mail.Read**: Permite ler emails
- **Mail.Send**: Permite enviar emails

Selecione ambas as permissões

**Passo 5:** Concordar com as Permissões
1. Clique em **"Add permissions"**
2. Você verá ambas as permissões adicionadas, mas com status "NOT GRANTED"
3. Clique em **"Grant admin consent for [Tenant Name]"** (botão cinza no topo)
4. Clique em **"Yes"** para confirmar

**Passo 6:** Verificar Status
- Depois de consentir, o status muda para ✅ "Granted"

---

## 📋 Resumo Técnico

### Arquitetura Nova

```
Usuário/Sistema
    ↓
EmailClient (OAuth2 + MSAL)
    ↓
Microsoft Graph API
    ↓
Microsoft Office365 / Outlook
```

### Mudanças Principais no Código

**Antes (BasicAuth - BLOQUEADO):**
```python
mail = imaplib.IMAP4_SSL("outlook.office365.com", 993)
mail.login(email, password)  # ❌ BLOCKED by tenant policy
```

**Depois (OAuth2 - FUNCIONAL):**
```python
app = msal.ConfidentialClientApplication(...)
token = app.acquire_token_for_client(scopes=[...])
headers = {"Authorization": f"Bearer {token}"}
response = requests.get("https://graph.microsoft.com/v1.0/users/{email}/mailFolders/inbox/messages", headers=headers)
```

### Endpoints Utilizados

| Operação | Endpoint |
|----------|----------|
| Ler Emails | `GET /users/{email}/mailFolders/inbox/messages` |
| Enviar Email | `POST /users/{email}/sendMail` |
| Listar Pastas | `GET /users/{email}/mailFolders` |
| Buscar Pasta Específica | `GET /users/{email}/mailFolders?$filter=displayName eq 'nome'` |

---

## 🧪 Como Testar Após Adicionar Permissões

```bash
cd C:\Users\João Luccas\Desktop\LINKB2B\hierarchy-mapper
python tmp/test_graph_api_oauth2.py
```

Saída esperada:
```
======================================================================
🚀 TESTE DE INTEGRAÇÃO: Microsoft Graph API com OAuth2
======================================================================
======================================================================
🔐 TESTE 1: Autenticação OAuth2
======================================================================
✅ Autenticação bem-sucedida!
   Email: joao.moura@jferres.com.br
   Tenant ID: e810eb4d-9b69-4af6-853c-4b50e0d7573f

======================================================================
📧 TESTE 2: Buscar e-mails não lidos da Inbox
======================================================================
✅ 5 e-mail(s) não lido(s) encontrado(s):

--- E-mail 1 ---
De: cliente@example.com
Assunto: Seguimento de Proposta
Prévia: Olá, gostaria de saber mais sobre...
```

---

## 🔒 Segurança & Boas Práticas

### ✅ Implementado
- OAuth2 (nunca armazena senha em plain text)
- Tokens expíram automaticamente
- Escopo limitado (.default = permissões explícitas apenas)
- Client Secret armazenado no `.env` (não em código)

### ⚠️ Recomendações Futuras
- [ ] Implementar token refresh automático
- [ ] Adicionar logging estruturado de tentativas de acesso
- [ ] Monitorar uso da API para detectar anomalias
- [ ] Usar Azure Key Vault para armazenar secrets em produção (em vez de `.env`)

---

## 📞 Suporte

### Se não conseguir adicionar permissões:
- Entre em contato com o TI Department da JFerres
- Compartilhe este documento com eles
- Eles precisarão de acesso admin ao Entra portal

### Erro "ErrorAccessDenied" após adicionar permissões?
- Aguarde 5-10 minutos para o tenant cache ser atualizado
- Teste novamente com `python tmp/test_graph_api_oauth2.py`

### Erro de "Not Enough Privileges"?
- Você precisa ser admin do tenant JFerres
- Alguém com role de "Global Administrator" ou "Application Administrator" precisa fazer esse setup

---

## 📁 Arquivos Modificados

```
✅ backend/.env                                         (credenciais OAuth adicionadas)
✅ backend/requirements.txt                             (msal + requests adicionados)
✅ backend/services/communication/email_client.py       (refatorado para Graph API)
✅ tmp/test_graph_api_oauth2.py                         (novo teste OAuth2)
```

---

## 🎯 Próxima Etapa

1. **Você (ou TI JFerres):** Adicione as permissões no Azure portal (Mail.Read + Mail.Send)
2. **Você:** Execute o teste: `python tmp/test_graph_api_oauth2.py`
3. **Sistema:** Quando permissões forem concedidas, o email system funcionará 100%!

---

**Data de Implementação:** 14/04/2026
**Status:** Aguardando configuração de permissões no Azure portal
