param(
    [string]$ProjectPath = "D:\SEALINK WEB"
)

$ErrorActionPreference = "Stop"
$backendPath = Join-Path $ProjectPath "backend"
$venvPython = Join-Path $backendPath ".venv\Scripts\python.exe"
$python = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { "python" }

Push-Location $backendPath
try {
    & $python -m app.services.backup_service
    if ($LASTEXITCODE -ne 0) {
        throw "Backup process exited with code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
