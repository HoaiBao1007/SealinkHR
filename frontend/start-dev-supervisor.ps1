param(
    [int]$Port = 5174
)

$ErrorActionPreference = "Continue"
$frontendRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$logDirectory = Join-Path $frontendRoot "logs"
$logFile = Join-Path $logDirectory "vite-supervisor.log"
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
Set-Location $frontendRoot

while ($true) {
    Add-Content -LiteralPath $logFile -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Starting Vite on port $Port"
    & npm.cmd run dev -- --host 0.0.0.0 --port $Port --strictPort *>> $logFile
    $exitCode = $LASTEXITCODE
    Add-Content -LiteralPath $logFile -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Vite exited with code $exitCode. Restarting in 2 seconds."
    Start-Sleep -Seconds 2
}
