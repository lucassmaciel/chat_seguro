# Script PowerShell para iniciar múltiplos clientes em portas diferentes
# Uso: .\start-clients.ps1

Write-Host "Iniciando múltiplos clientes do Chat Seguro..." -ForegroundColor Cyan
Write-Host ""

# Verificar se o node_modules existe
if (-not (Test-Path "node_modules")) {
    Write-Host "Instalando dependências..." -ForegroundColor Yellow
    npm install
}

# Iniciar clientes em portas diferentes
Write-Host "Cliente 1 na porta 3000..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD'; npm run dev:3000"

Start-Sleep -Seconds 2

Write-Host "Cliente 2 na porta 3001..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD'; npm run dev:3001"

Start-Sleep -Seconds 2

Write-Host "Cliente 3 na porta 3002..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD'; npm run dev:3002"

Write-Host ""
Write-Host "Clientes iniciados!" -ForegroundColor Cyan
Write-Host "Acesse:" -ForegroundColor Yellow
Write-Host "  - Cliente 1: http://localhost:3000" -ForegroundColor White
Write-Host "  - Cliente 2: http://localhost:3001" -ForegroundColor White
Write-Host "  - Cliente 3: http://localhost:3002" -ForegroundColor White
Write-Host ""
Write-Host "Pressione qualquer tecla para fechar este script (os clientes continuarão rodando)..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

