@echo off
title GERENCIADOR-LINKB2B
echo 🚀 Iniciando Ambiente de Desenvolvimento LINKB2B...

:: 1. Limpeza de processos e janelas de SERVIÇO antigas
echo 🧹 Limpando servicos e terminais antigos...

:: Mata as janelas de PowerShell pelo título (muito eficaz para fechar o terminal)
taskkill /f /fi "WINDOWTITLE eq LINKB2B-SVC-*" /t >nul 2>&1

:: Limpa processos específicos que costumam travar portas
taskkill /f /im node.exe /t >nul 2>&1
taskkill /f /im python.exe /t >nul 2>&1
taskkill /f /im redis-server.exe /t >nul 2>&1

:: Aguarda um segundo para garantir a liberação das portas
timeout /t 1 /nobreak > nul

:: 2. Iniciar Redis em segundo plano (se existir na pasta)
if exist "backend\redis\redis-server.exe" (
    echo 🔴 Iniciando Redis e limpando filas...
    :: Usar pushd para garantir que o diretório corrente seja preservado
    pushd backend\redis
    start /b redis-server.exe "redis.windows.conf"
    popd
    timeout /t 2 /nobreak > nul
    if exist "backend\redis\redis-cli.exe" (
        pushd backend\redis
        redis-cli.exe FLUSHALL >nul 2>&1
        popd
        echo ✅ Fila de tarefas limpa!
    )
) else (
    echo ⚠️ Redis nao encontrado em backend\redis.
)

:: 3. Iniciar Backend (FastAPI)
echo 🐍 Iniciando Backend (Porta 8000)...
start "LINKB2B-SVC-Backend" cmd /k "cd backend && watchfiles ^"uvicorn main:app --port 8000^" ."

:: 4. Iniciar Worker (Arq)
echo 🛠️ Iniciando Worker...
start "LINKB2B-SVC-Worker" cmd /k "cd backend && watchfiles ^"arq services.worker.WorkerSettings^" ."

:: 5. Iniciar Frontend (Next.js dev)
echo ⚛️ Iniciando Frontend (Porta 3000)...
start "LINKB2B-SVC-Frontend" cmd /k "cd frontend && npm run dev"

:: 6. Iniciar Servico WhatsApp (Node)
echo 💬 Iniciando Servico WhatsApp (Porta 8001)...
start "LINKB2B-SVC-WhatsApp" cmd /k "cd backend\services\whatsapp-service && npm start"

echo.
echo ✅ Tudo pronto! Verifique as janelas abertas.
echo 💡 URLs:
echo    - Frontend:  http://localhost:3000
echo    - Backend:   http://localhost:8000
echo    - Swagger:   http://localhost:8000/docs
echo    - WhatsApp:  http://localhost:8001
echo.
echo 💡 Dica: Se algo travar, rode este script novamente para limpar e subir tudo.
pause
