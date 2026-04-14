# 🔧 Troubleshooting: Drawer não carrega dados

## ❌ Problema Encontrado

```
[NetworkGraph] Erro ao carregar empresas do Pipedrive: Failed to fetch
127.0.0.1:8000/api/v1/pipedrive/organizations → net::ERR_CONNECTION_RESET
```

### Causa Raiz
Watchfiles detectou **130 mudanças** nos arquivos backend → reiniciou uvicorn múltiplas vezes → conexões foram abortadas meio do caminho.

```
[07:42:02] 130 changes detected  ← Restart do backend!
INFO:     Started server process [7856]
INFO:     Started server process [15380]  ← Reiniciou NOVAMENTE!
```

Enquanto isso, frontend tentava carregar dados e recebeu `ERR_CONNECTION_RESET`.

---

## ✅ Solução: Use versão ESTÁVEL

### Opção 1: Usar uvicorn com --reload (RECOMENDADO)
```powershell
.\rodar_dev_stable.ps1
```

**Vantagens:**
- ✅ Auto-reload apenas de mudanças de código (não .pyc, __pycache__)
- ✅ Mais estável que watchfiles
- ✅ Mesma experiência de dev

**Como funciona:**
- Uvicorn monitora apenas `*.py` 
- Ignora arquivos compilados automaticamente
- Restarts são mais rápidos e menos frequentes

---

### Opção 2: Sem auto-reload (MÁXIMA ESTABILIDADE)
Se quiser máxima estabilidade, edite `rodar_dev_stable.ps1` e remova `--reload`:

```powershell
# Mude de:
uvicorn main:app --port 8000 --reload

# Para:
uvicorn main:app --port 8000
```

---

## 🔍 Por que watchfiles gera 130 mudanças?

Watchfiles monitora **TUDO** incluindo:
- ✅ Arquivos `.py` (código)
- ❌ `__pycache__/` (compilados)
- ❌ `*.pyc` (cache Python)
- ❌ `.sqlite` / `.db` (banco de dados)
- ❌ Arquivos temporários
- ❌ Logs

Resultado: Reinicia backend 20+ vezes por minuto!

---

## 📋 Guardar URLs de APIs

Depois que backend está estável, verifique:

```
GET http://localhost:8000/docs
     ↓
Swagger mostra todas as rotas disponíveis
```

Se ainda ver `ERR_CONNECTION_RESET`, verifique:
1. Backend realmente rodando: `curl http://127.0.0.1:8000/docs`
2. Se há erro Python: Veja logs da janela do Backend
3. Se falta rota: Verifique `backend/api/v1/endpoints/pipedrive.py`

---

## 🎯 Próximos Passos

1. Rode: `.\rodar_dev_stable.ps1`
2. Aguarde 5 segundos (sem reinícios)
3. Acesse: http://localhost:3000
4. Clique em um Drawer - deve carregar! ✅

Se ainda houver erro, compartilhe os logs da janela Backend.
