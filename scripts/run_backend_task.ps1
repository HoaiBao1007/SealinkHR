[CmdletBinding()]
param(
    [string]$AppPath = "C:\SEALINK\app",
    [string]$LogDirectory = "C:\SEALINK\logs",
    [ValidateRange(1, 65535)]
    [int]$BackendPort = 8001
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$backendPath = Join-Path $AppPath "backend"
$python = Join-Path $backendPath ".venv\Scripts\python.exe"
$backendEnv = Join-Path $backendPath ".env"
foreach ($path in @($backendPath, $python, $backendEnv)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Missing backend runtime path: $path"
    }
}

New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
$stdoutLog = Join-Path $LogDirectory "backend-service.stdout.log"
$stderrLog = Join-Path $LogDirectory "backend-service.stderr.log"

Add-Content -LiteralPath $stdoutLog -Value "[$(Get-Date -Format o)] Starting SEALINK backend on port $BackendPort"
Push-Location $backendPath
try {
    & $python -m uvicorn app.main:app --host 0.0.0.0 --port $BackendPort 1>> $stdoutLog 2>> $stderrLog
    $exitCode = $LASTEXITCODE
} finally {
    Pop-Location
}

Add-Content -LiteralPath $stderrLog -Value "[$(Get-Date -Format o)] Backend exited with code $exitCode"
exit $exitCode

