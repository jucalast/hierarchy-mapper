# 🔐 Guia Correto: Adicionar Permissões de APLICAÇÃO (não Delegado)

## ⚠️ Problema Identificado

Você viu permissões do tipo **"Delegado"** (Delegated), mas nosso app precisa de **"Aplicação"** (Application).

```
❌ ERRADO (Delegado):
   - Requer usuário autenticado
   - Não funciona com Client Credentials Flow
   - Exigem consentimento do usuário final

✅ CERTO (Aplicação):
   - Funciona sem usuário específico
   - Compatível com Client Credentials Flow
   - Requer apenas consentimento do admin do tenant
```

---

## 📍 Passos Corretos no Azure Portal

### 1️⃣ Acesse o Entra Admin Center
```
URL: https://entra.microsoft.com/
Login: Conta corporativa JFerres
```

### 2️⃣ Navegue até a App Registration
```
Left Sidebar
  ↓
Applications (ou Aplicações)
  ↓
App registrations (ou Registros de Aplicativos)
  ↓
Procure: "LinkB2B Email Sync" (ou veja em "All applications")
  ↓
Clique para abrir
```

### 3️⃣ Ir para API Permissions
```
No sidebar da app:
  ↓
API permissions (ou Permissões de API)
```

### 4️⃣ ⭐️ SELECIONE "Application permissions" (NÃO Delegated!)
```
Clique: "+ Add a permission"
  ↓
Selecione: "Microsoft Graph"
  ↓
IMPORTANTE: Escolha "Application permissions" 
            (não "Delegated permissions")
  ↓
```

### 5️⃣ Busque e Selecione as Permissões

Na caixa de busca, procure por:

#### Permissão 1: Mail.Read (Application)
```
Tipo: Application permissions
Status: Você verá apenas versões de "Delegado" nesse ponto
```

Se só vir "Mail.Read" (Delegado), procure por:
- **Mail.ReadAll** (Application) ← Use ESSA

#### Permissão 2: Mail.Send (Application)
```
Na mesma busca, busque por "Mail.Send"
Procure por: **Mail.SendAsUser** (Application) ou
             **Mail.Send** com tipo "Application"
```

Se houver **Mail.SendAsUser** (Application), use essa.

### 6️⃣ Selecione Ambas e Clique "Add permissions"

Depois de adicionar, você verá:
```
✓ Mail.ReadAll (Application)  - Status: [precisa de consent]
✓ Mail.SendAsUser (Application) - Status: [precisa de consent]
```

### 7️⃣ Grant Admin Consent

```
No topo da página "API permissions":
  ↓
Botão cinza: "Grant admin consent for [seu tenant]"
  ↓
Clique e confirme "Yes"
  ↓
Status muda para: ✅ "Granted"
```

---

## 🔍 Permissões Corretas de Aplicação

Para Microsoft Graph (Application-only):

| Permissão | Tipo | Uso | Consentimento |
|-----------|------|-----|--------------|
| **Mail.ReadAll** | Application | Ler todos os emails | Admin |
| **Mail.SendAsUser** | Application | Enviar email como usuário | Admin |
| **Mail.Send** | Application | Enviar mail (se disponível) | Admin |
| **User.Read.All** | Application | Ler dados de usuários | Admin |

---

## ❓ Se Não Conseguir Encontrar?

### Opção 1: Procure por "Mail.ReadAll"
```
Search box → "Mail.ReadAll"
Confirme que é do tipo "Application" 
Selecione
```

### Opção 2: Procure por "Send"
```
Search box → "Mail.SendAsUser"
ou
Search box → "Mail.Send"
Confirme que é tipo "Application"
Selecione
```

### Opção 3: Se Ainda Assim Não Aparecer
Pode ser que:
- ✅ As permissões já estejam adicionadas (veja embaixo da página)
- ⚠️ Você não tem permissões de admin para adicionar
- ⚠️ O app precisa de outras escopos

---

## ✅ Como Verificar Depois de Adicionar

```
Na página "API permissions" você deve ver:

✅ Mail.ReadAll (Application) - Granted
✅ Mail.SendAsUser (Application) - Granted
(ou Mail.Send - Application - Granted)

Se ambas mostram ✅ Granted:
  → Parabéns! Próximo passo é rodar o teste
```

---

## 🚀 Testar Depois de Conceder Permissões

```bash
# No terminal (na pasta do projeto)
python tmp/test_graph_api_oauth2.py

# Saída esperada:
# ✅ Autenticação OAuth2: Sucesso
# ✅ Buscar e-mails: 5 e-mail(s) encontrado(s)
# ✅ Enviar e-mail: Sucesso
```

---

## 🎯 Resumo Visual

```
❌ ERRADO (o que você viu):
   Microsoft Graph (Delegated permissions):
   - Mail.Read [Delegado] ← NÃO USE ISSO
   - Mail.Send [Delegado] ← NÃO USE ISSO

✅ CERTO (o que você precisa):
   Microsoft Graph (Application permissions):
   - Mail.ReadAll [Application] ← USE ISSO
   - Mail.SendAsUser [Application] ← USE ISSO
   
   Depois: Grant admin consent ✓
```

---

## 💡 Se Tiver Dúvidas

1. **"Não consigo encontrar Application permissions"**
   - Clique em "+ Add a permission"
   - Microsoft Graph
   - Procure por "Application permissions" no dropdown/abas

2. **"Vejo só Delegated"**
   - Você pode estar em "Delegated permissions"
   - Mude para "Application permissions"
   - Procure novamente

3. **"Não tenho permissão para adicionar"**
   - Você precisa de role "Application Administrator" ou "Global Administrator"
   - Contate o TI da JFerres

---

**Tente novamente com esses passos e me avisa se conseguir!** 🚀
