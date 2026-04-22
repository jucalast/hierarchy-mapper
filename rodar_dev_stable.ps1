# Script PowerShell para iniciar ambiente sem watchfiles (sem auto-reload)
# Use este quando quiser estabilidade em vez de dev automático

$ErrorActionPreference = "SilentlyContinue"
$OutputEncoding = [console]::InputEncoding = [console]::OutputEncoding = New-Object System.Text.UTF8Encoding
$env:PYTHONUTF8=1

Write-Host "🚀 Iniciando Ambiente de Desenvolvimento LINKB2B (SEM AUTO-RELOAD)..." -ForegroundColor Green
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

# 3. Iniciar Backend (SEM watchfiles - apenas uvicorn)
$backendPath = Join-Path $PSScriptRoot "backend"
$pythonPath = Join-Path $backendPath "venv\Scripts\python.exe"

Write-Host "🐍 Iniciando Backend (Porta 8000 - SEM AUTO-RELOAD)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "
    `$Host.UI.RawUI.WindowTitle='LINKB2B-SVC-Backend'
    Set-Location '$backendPath'
    Write-Host 'ℹ️ Backend iniciado. Pressione Ctrl+C para parar.' -ForegroundColor Yellow
    Write-Host 'Para mudanças automáticas, use: .\rodar_dev.ps1' -ForegroundColor Cyan
    & '$pythonPath' -X utf8 -m uvicorn main:app --port 8000
"

# 4. Iniciar Worker (SEM watchfiles)
Write-Host "🛠️ Iniciando Worker (SEM AUTO-RELOAD)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "
    `$Host.UI.RawUI.WindowTitle='LINKB2B-SVC-Worker'
    Set-Location '$backendPath'
    Write-Host 'ℹ️ Worker iniciado. Pressione Ctrl+C para parar.' -ForegroundColor Yellow
    & '$pythonPath' -m arq services.worker.WorkerSettings
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

# 7. Iniciar Email Service (Python)
Write-Host "📧 Iniciando Servico de Email (Porta 8002)..." -ForegroundColor Cyan
$emailPath = Join-Path $PSScriptRoot "backend\services\email-service"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "
    `$Host.UI.RawUI.WindowTitle='LINKB2B-SVC-Email'
    Set-Location '$emailPath'
    & '$pythonPath' -X utf8 main.py
"

Write-Host ""
Write-Host "✅ Tudo pronto! Versão ESTÁVEL (sem auto-reload)." -ForegroundColor Green
Write-Host ""
Write-Host "💡 URLs:" -ForegroundColor Yellow
Write-Host "   - Frontend:  http://localhost:3000" -ForegroundColor Cyan
Write-Host "   - Backend:   http://localhost:8000" -ForegroundColor Cyan
Write-Host "   - Swagger:   http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "   - WhatsApp:  http://localhost:8001" -ForegroundColor Cyan
Write-Host "   - Email:     http://localhost:8002" -ForegroundColor Cyan
Write-Host ""
Write-Host "📝 Versões:" -ForegroundColor Yellow
Write-Host "   - rodar_dev.ps1: COM watchfiles (auto-reload de código)" -ForegroundColor Cyan
Write-Host "   - rodar_dev_stable.ps1: SEM watchfiles (estável)" -ForegroundColor Cyan
