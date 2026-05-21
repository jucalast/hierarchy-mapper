# Script PowerShell para iniciar ambiente COM watchfiles (auto-reload de código)

$ErrorActionPreference = "SilentlyContinue"
$OutputEncoding = [console]::InputEncoding = [console]::OutputEncoding = New-Object System.Text.UTF8Encoding
$env:PYTHONUTF8=1

Write-Host "Iniciando Ambiente de Desenvolvimento LINKB2B (COM HOT-RELOAD)..." -ForegroundColor Green
Write-Host ""

# --- Verificar Ollama local ---
Write-Host "Verificando Ollama local..." -ForegroundColor Cyan
try {
    $ollamaCheck = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -Method Get -TimeoutSec 5
    Write-Host "Ollama online com $(($ollamaCheck.models).Count) modelo(s)." -ForegroundColor Green
} catch {
    Write-Host "Ollama nao esta rodando. Iniciando..." -ForegroundColor Yellow
    Start-Process "ollama" -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 3
    Write-Host "Ollama iniciado." -ForegroundColor Green
}

# 1. Limpar processos antigos
Write-Host "Limpando servicos e terminais antigos..." -ForegroundColor Yellow
Get-Process | Where-Object { $_.MainWindowTitle -like "*LINKB2B-*" } | Stop-Process -Force
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process node -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process headless_shell -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process chrome -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 1

# 2. Iniciar Redis
$redisPath = Join-Path $PSScriptRoot "backend\redis\redis-server.exe"
$redisConf = Join-Path $PSScriptRoot "backend\redis\redis.windows.conf"
$redisCliPath = Join-Path $PSScriptRoot "backend\redis\redis-cli.exe"

if ((Test-Path $redisPath) -and (Test-Path $redisConf)) {
    Write-Host "Iniciando Redis..." -ForegroundColor Cyan
    try {
        Push-Location (Split-Path -Parent $redisPath)
        & (Get-Item $redisPath).FullName (Get-Item $redisConf).FullName 2>$null &
        Pop-Location
        Start-Sleep -Seconds 2
        if (Test-Path $redisCliPath) {
            & (Get-Item $redisCliPath).FullName FLUSHALL 2>$null
            Write-Host "Fila de tarefas limpa!" -ForegroundColor Green
        }
    } catch {
        Write-Host "Erro ao iniciar Redis: $_" -ForegroundColor Yellow
    }
} else {
    Write-Host "Redis nao encontrado" -ForegroundColor Yellow
}

# 3. Iniciar Backend (COM watchfiles via --reload)
$backendPath = Join-Path $PSScriptRoot "backend"
$pythonPath = Join-Path $backendPath "venv\Scripts\python.exe"

Write-Host "Iniciando Backend (Porta 8000 - COM AUTO-RELOAD)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "
    `$Host.UI.RawUI.WindowTitle='LINKB2B-SVC-Backend'
    Set-Location '$backendPath'
    & '$pythonPath' -X utf8 -m uvicorn main:app --port 8000 --reload ``
        --reload-dir api ``
        --reload-dir core ``
        --reload-dir models ``
        --reload-dir modules ``
        --reload-dir services ``
        --reload-exclude '__pycache__' ``
        --reload-exclude '*.pyc' ``
        --reload-exclude '*.tmp' ``
        --reload-exclude '*.db' ``
        --reload-exclude '*.db-journal' ``
        --reload-exclude '*.db-wal' ``
        --reload-exclude 'intelligence.db*' ``
        --reload-exclude '*.log'
"

# 4. Iniciar Worker (COM watchfiles)
Write-Host "Iniciando Worker (COM AUTO-RELOAD)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "
    `$Host.UI.RawUI.WindowTitle='LINKB2B-SVC-Worker'
    Set-Location '$backendPath'
    & '$pythonPath' -m watchfiles --filter python ``
        'arq services.worker.WorkerSettings' ``
        api core models modules services ``
        --ignore-paths '__pycache__,.pytest_cache,*.db,intelligence.db,*.log,*.tmp'
"

# 5. Iniciar Frontend
Write-Host "Iniciando Frontend (Porta 3000)..." -ForegroundColor Cyan
$frontendPath = Join-Path $PSScriptRoot "frontend"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "
    `$Host.UI.RawUI.WindowTitle='LINKB2B-SVC-Frontend'
    Set-Location '$frontendPath'
    npm run dev
"

# 6. Iniciar WhatsApp Service
Write-Host "Iniciando Servico WhatsApp (Porta 8001)..." -ForegroundColor Cyan
$whatsappPath = Join-Path $PSScriptRoot "backend\whatsapp-service"
if (Test-Path $whatsappPath) {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "
        `$Host.UI.RawUI.WindowTitle='LINKB2B-SVC-WhatsApp'
        Set-Location '$whatsappPath'
        npm start
    "
} else {
    Write-Host "WhatsApp service nao encontrado em $whatsappPath" -ForegroundColor Yellow
}

# 7. Iniciar Email Service
Write-Host "Iniciando Servico de Email (Porta 8002 - COM AUTO-RELOAD)..." -ForegroundColor Cyan
$emailPath = Join-Path $PSScriptRoot "backend\services\email-service"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "
    `$Host.UI.RawUI.WindowTitle='LINKB2B-SVC-Email'
    Set-Location '$emailPath'
    & '$pythonPath' -X utf8 -m uvicorn main:app --port 8002 --reload --reload-dir .
"

Write-Host ""
Write-Host "Tudo pronto! (com auto-reload)" -ForegroundColor Green
Write-Host ""
Write-Host "URLs:" -ForegroundColor Yellow
Write-Host "   Frontend:  http://localhost:3000" -ForegroundColor Cyan
Write-Host "   Backend:   http://localhost:8000" -ForegroundColor Cyan
Write-Host "   Swagger:   http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "   WhatsApp:  http://localhost:8001" -ForegroundColor Cyan
Write-Host "   Email:     http://localhost:8002" -ForegroundColor Cyan
