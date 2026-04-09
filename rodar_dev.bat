@echo off
title LINKB2B Dev Environment
echo 🚀 Iniciando Ambiente de Desenvolvimento LINKB2B...

:: 1. Limpeza de processos fantasmas (Windows)
echo 🧹 Limpando processos antigos...
taskkill /f /im python.exe /t >nul 2>&1
taskkill /f /im node.exe /t >nul 2>&1
taskkill /f /im redis-server.exe /t >nul 2>&1

:: 2. Iniciar Redis em segundo plano (se existir na pasta)
if exist "backend\redis\redis-server.exe" (
    echo 🔴 Iniciando Redis e limpando filas...
    start /b "" "backend\redis\redis-server.exe" "backend\redis\redis.windows.conf"
    timeout /t 2 /nobreak > nul
    if exist "backend\redis\redis-cli.exe" (
        "backend\redis\redis-cli.exe" FLUSHALL > nul 2>&1
        echo ✅ Fila de tarefas limpa!
    )
) else (
    echo ⚠️ Redis nao encontrado em backend\redis. Certifique-se que o Redis esta rodando.
)

:: 3. Iniciar Backend (FastAPI) com auto-reload inteligente (Ignora DB e Logs)
echo 🐍 Iniciando Backend (Porta 8000)...
start powershell -NoExit -Command "cd backend; watchfiles --ignore-paths 'intelligence.db,logs,__pycache__' 'uvicorn main:app --port 8000' ."

:: 4. Iniciar Worker (Arq) com auto-reload inteligente
echo 🛠️ Iniciando Worker com Auto-Reload...
start powershell -NoExit -Command "cd backend; watchfiles --ignore-paths 'intelligence.db,logs,__pycache__' 'arq services.worker.WorkerSettings' ."

:: 5. Iniciar Frontend (Vite)
echo ⚛️ Iniciando Frontend (Porta 5173)...
start powershell -NoExit -Command "cd frontend; npm run dev"

echo ✅ Tudo pronto! Verifique as janelas abertas.
echo 💡 Dica: Se algo travar, rode este script novamente para limpar e subir tudo.
pause
