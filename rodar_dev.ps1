# Script PowerShell para iniciar ambiente de desenvolvimento sem erros cosmEticos
# Alternativa ao rodar_dev.bat que pode ter problemas de quote no PowerShell

$ErrorActionPreference = "SilentlyContinue"

Write-Host "🚀 Iniciando Ambiente de Desenvolvimento LINKB2B..." -ForegroundColor Green
Write-Host ""

# 1. Limpar processos antigos
Write-Host "🧹 Limpando servicos e terminais antigos..." -ForegroundColor Yellow
Get-Process | Where-Object { $_.MainWindowTitle -like "*LINKB2B-SVC-*" } | Stop-Process -Force
Get-Process node -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process redis-server -ErrorAction SilentlyContinue | Stop-Process -Force

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
        
        # Inicia Redis mudando para seu diretório antes
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
    if (-not (Test-Path $redisPath)) {
        Write-Host "⚠️ Redis não encontrado em: $redisPath" -ForegroundColor Yellow
    }
    if (-not (Test-Path $redisConf)) {
        Write-Host "⚠️ Arquivo de configuração Redis não encontrado em: $redisConf" -ForegroundColor Yellow
    }
}

# 3. Iniciar Backend
Write-Host "🐍 Iniciando Backend (Porta 8000)..." -ForegroundColor Cyan
$backendPath = Join-Path $PSScriptRoot "backend"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "
    `$Host.UI.RawUI.WindowTitle='LINKB2B-SVC-Backend'
    Set-Location '$backendPath'
    watchfiles 'uvicorn main:app --port 8000' .
"

# 4. Iniciar Worker
Write-Host "🛠️ Iniciando Worker..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "
    `$Host.UI.RawUI.WindowTitle='LINKB2B-SVC-Worker'
    Set-Location '$backendPath'
    watchfiles 'arq services.worker.WorkerSettings' .
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

Write-Host ""
Write-Host "✅ Tudo pronto! Verifique as janelas abertas." -ForegroundColor Green
Write-Host ""
Write-Host "💡 URLs:" -ForegroundColor Yellow
Write-Host "   - Frontend:  http://localhost:3000" -ForegroundColor Cyan
Write-Host "   - Backend:   http://localhost:8000" -ForegroundColor Cyan
Write-Host "   - Swagger:   http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "   - WhatsApp:  http://localhost:8001" -ForegroundColor Cyan
Write-Host ""
Write-Host "💡 Dica: Se algo travar, execute o script novamente para limpar e subir tudo." -ForegroundColor Yellow
