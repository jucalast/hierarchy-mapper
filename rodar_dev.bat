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
    start /b "LINKB2B-SVC-Redis" "backend\redis\redis-server.exe" "backend\redis\redis.windows.conf"
    timeout /t 2 /nobreak > nul
    if exist "backend\redis\redis-cli.exe" (
        "backend\redis\redis-cli.exe" FLUSHALL > nul 2>&1
        echo ✅ Fila de tarefas limpa!
    )
) else (
    echo ⚠️ Redis nao encontrado em backend\redis.
)

:: 3. Iniciar Backend (FastAPI) - Adicionado -NoExit para voce ver se der erro
echo 🐍 Iniciando Backend (Porta 8000)...
start powershell -NoExit -Command "$Host.UI.RawUI.WindowTitle='LINKB2B-SVC-Backend'; cd backend; watchfiles --ignore-paths 'intelligence.db,logs,__pycache__' 'uvicorn main:app --port 8000' ."

:: 4. Iniciar Worker (Arq)
echo 🛠️ Iniciando Worker...
start powershell -NoExit -Command "$Host.UI.RawUI.WindowTitle='LINKB2B-SVC-Worker'; cd backend; watchfiles --ignore-paths 'intelligence.db,logs,__pycache__' 'arq services.worker.WorkerSettings' ."

:: 5. Iniciar Frontend (Vite)
echo ⚛️ Iniciando Frontend (Porta 5173)...
start powershell -NoExit -Command "$Host.UI.RawUI.WindowTitle='LINKB2B-SVC-Frontend'; cd frontend; npm run dev"

echo ✅ Tudo pronto! Verifique as janelas abertas.
echo 💡 Dica: Se algo travar, rode este script novamente para limpar e subir tudo.
pause
