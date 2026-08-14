# Starts the portable backend and the supervised Vite frontend in separate processes.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontendDir = Join-Path $root "frontend"
$backendDir = Join-Path $root "backend"

Write-Host "Starting SEALINK services..." -ForegroundColor Cyan

Start-Process -FilePath "powershell.exe" -ArgumentList @(
    "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", "Set-Location `"$backendDir`"; & .\start-portable.ps1"
) -WorkingDirectory $backendDir -WindowStyle Normal

if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
    Write-Host "frontend/node_modules is missing. Run npm install in frontend, then start this script again." -ForegroundColor Yellow
    exit 1
}

$frontendSupervisor = Join-Path $frontendDir "start-dev-supervisor.ps1"
Start-Process -FilePath "powershell.exe" -ArgumentList @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$frontendSupervisor`"", "-Port", "5174"
) -WorkingDirectory $frontendDir -WindowStyle Hidden

for ($attempt = 1; $attempt -le 15; $attempt++) {
    if (Get-NetTCPConnection -LocalPort 5174 -State Listen -ErrorAction SilentlyContinue) { break }
    Start-Sleep -Seconds 1
}

if (Get-NetTCPConnection -LocalPort 5174 -State Listen -ErrorAction SilentlyContinue) {
    Write-Host "Frontend supervisor: http://localhost:5174" -ForegroundColor Green
} else {
    Write-Host "Frontend did not start. See frontend/logs/vite-supervisor.log" -ForegroundColor Red
}
Write-Host "Backend: http://localhost:8001" -ForegroundColor Green
