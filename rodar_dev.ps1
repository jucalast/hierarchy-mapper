# Script PowerShell para iniciar ambiente COM watchfiles (auto-reload de código)
# Baseado na versão estável, mas otimizado para o desenvolvimento ágil

$ErrorActionPreference = "SilentlyContinue"
$OutputEncoding = [console]::InputEncoding = [console]::OutputEncoding = New-Object System.Text.UTF8Encoding
$env:PYTHONUTF8=1

Write-Host "🚀 Iniciando Ambiente de Desenvolvimento LINKB2B (COM HOT-RELOAD)..." -ForegroundColor Green
Write-Host ""

# 1. Limpar processos antigos
Write-Host "🧹 Limpando servicos e terminais antigos..." -ForegroundColor Yellow
Get-Process | Where-Object { $_.MainWindowTitle -like "*LINKB2B-*" } | Stop-Process -Force
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process node -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process headless_shell -ErrorAction SilentlyContinue | Stop-Process -Force

Start-Sleep -Seconds 1

# 2. Iniciar Redis
$redisPath = Join-Path $PSScriptRoot "backend\redis\redis-server.exe"
$redisConf = Join-Path $PSScriptRoot "backend\redis\redis.windows.conf"
$redisCliPath = Join-Path $PSScriptRoot "backend\redis\redis-cli.exe"

if ((Test-Path $redisPath) -and (Test-Path $redisConf)) {
    Write-Host "🔴 Iniciando Redis..." -ForegroundColor Cyan
    try {
        $redisDir = Split-Path -Parent $redisPath
        $redisFullPath = (Get-Item $redisPath).FullName
        $redisConfFullPath = (Get-Item $redisConf).FullName
        
        Push-Location $redisDir
        & $redisFullPath $redisConfFullPath 2>$null &
        Pop-Location
        
        Start-Sleep -Seconds 2
        
        if (Test-Path $redisCliPath) {
            $redisCliFullPath = (Get-Item $redisCliPath).FullName
            & $redisCliFullPath FLUSHALL 2>$null
            Write-Host "✅ Fila de tarefas limpa!" -ForegroundColor Green
        }
    } catch {
        Write-Host "⚠️ Erro ao iniciar Redis: $_" -ForegroundColor Yellow
    }
} else {
    Write-Host "⚠️ Redis não encontrado" -ForegroundColor Yellow
}

# 3. Iniciar Backend (COM watchfiles via --reload)
$backendPath = Join-Path $PSScriptRoot "backend"
$pythonPath = Join-Path $backendPath "venv\Scripts\python.exe"

Write-Host "🐍 Iniciando Backend (Porta 8000 - COM AUTO-RELOAD)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "
    `$Host.UI.RawUI.WindowTitle='LINKB2B-SVC-Backend'
    Set-Location '$backendPath'
    Write-Host 'ℹ️ Backend iniciado com HOT-RELOAD ativo.' -ForegroundColor Yellow
    & '$pythonPath' -X utf8 -m uvicorn main:app --port 8000 --reload --reload-dir api --reload-dir core --reload-dir models --reload-dir services/ai --reload-dir services/communication --reload-dir services/context --reload-dir services/external --reload-dir services/hierarchy --reload-dir services/intelligence --reload-dir services/pipedrive --reload-dir services/whatsapp --reload-exclude '__pycache__' --reload-exclude '*.pyc' --reload-exclude '*.tmp' --reload-exclude '*.db' --reload-exclude '*.db-journal'
"

# 4. Iniciar Worker (COM watchfiles)
Write-Host "🛠️ Iniciando Worker (COM AUTO-RELOAD)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "
    `$Host.UI.RawUI.WindowTitle='LINKB2B-SVC-Worker'
    Set-Location '$backendPath'
    Write-Host 'ℹ️ Worker iniciado com WATCHFILES ativo.' -ForegroundColor Yellow
    & '$pythonPath' -m watchfiles 'arq services.worker.WorkerSettings' api core models services/ai services/communication services/context services/external services/hierarchy services/intelligence services/pipedrive services/whatsapp services/worker.py services/context_service.py services/whatsapp_integration.py services/whatsapp_resolver.py --ignore-paths '__pycache__,.pytest_cache,*.pyc,*.tmp,*.db,*.db-journal'
"

# 5. Iniciar Frontend
Write-Host "⚛️ Iniciando Frontend (Porta 3000)..." -ForegroundColor Cyan
$frontendPath = Join-Path $PSScriptRoot "frontend"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "
    `$Host.UI.RawUI.WindowTitle='LINKB2B-SVC-Frontend'
    Set-Location '$frontendPath'
    npm run dev
"

# 6. Iniciar WhatsApp Service
Write-Host "💬 Iniciando Servico WhatsApp (Porta 8001)..." -ForegroundColor Cyan
$whatsappPath = Join-Path $PSScriptRoot "backend\services\whatsapp-service"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "
    `$Host.UI.RawUI.WindowTitle='LINKB2B-SVC-WhatsApp'
    Set-Location '$whatsappPath'
    npm start
"

# 7. Iniciar Email Service (Python + Reload)
Write-Host "📧 Iniciando Servico de Email (Porta 8002 - COM AUTO-RELOAD)..." -ForegroundColor Cyan
$emailPath = Join-Path $PSScriptRoot "backend\services\email-service"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "
    `$Host.UI.RawUI.WindowTitle='LINKB2B-SVC-Email'
    Set-Location '$emailPath'
    & '$pythonPath' -X utf8 -m uvicorn main:app --port 8002 --reload --reload-dir . --reload-dir ../../services
"

Write-Host ""
Write-Host "✅ Tudo pronto! Versão DESENVOLVIMENTo (com auto-reload)." -ForegroundColor Green
Write-Host ""
Write-Host "💡 URLs:" -ForegroundColor Yellow
Write-Host "   - Frontend:  http://localhost:3000" -ForegroundColor Cyan
Write-Host "   - Backend:   http://localhost:8000" -ForegroundColor Cyan
Write-Host "   - WhatsApp:  http://localhost:8001" -ForegroundColor Cyan
Write-Host "   - Email:     http://localhost:8002" -ForegroundColor Cyan
Write-Host ""
Write-Host "📝 Versões:" -ForegroundColor Yellow
Write-Host "   - rodar_dev.ps1: COM watchfiles (auto-reload de código)" -ForegroundColor Cyan
Write-Host "   - rodar_dev_stable.ps1: SEM watchfiles (estável)" -ForegroundColor Cyan
