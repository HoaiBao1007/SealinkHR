[CmdletBinding()]
param(
    [string]$RunDirectory = "C:\SEALINK\run",
    [ValidateRange(1, 65535)]
    [int]$BackendPort = 8001,
    [ValidateRange(1, 65535)]
    [int]$FrontendPort = 8080,
    [switch]$KeepFirewallRules
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

foreach ($name in @("frontend-test.json", "backend-test.json")) {
    $stateFile = Join-Path $RunDirectory $name
    if (-not (Test-Path -LiteralPath $stateFile -PathType Leaf)) { continue }

    $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
    $process = Get-Process -Id ([int]$state.pid) -ErrorAction SilentlyContinue
    if ($process -and -not $process.HasExited) {
        $actualPath = $process.Path
        if ([IO.Path]::GetFullPath($actualPath) -ne [IO.Path]::GetFullPath([string]$state.executable)) {
            throw "PID $($state.pid) khong con la SEALINK Python process; khong dung process."
        }
        Stop-Process -Id $process.Id -Force
        $process.WaitForExit(10000) | Out-Null
        Write-Host "Stopped PID $($process.Id)"
    }
    Remove-Item -LiteralPath $stateFile -Force
}

if (-not $KeepFirewallRules) {
    foreach ($ruleName in @("SEALINK-Test-Backend-$BackendPort", "SEALINK-Test-Frontend-$FrontendPort")) {
        Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue |
            Remove-NetFirewallRule -ErrorAction Stop
    }
    Write-Host "Removed temporary SEALINK firewall rules."
}

Write-Host "SEALINK test server stopped." -ForegroundColor Green
