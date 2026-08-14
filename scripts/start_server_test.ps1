[CmdletBinding()]
param(
    [string]$AppPath = "C:\SEALINK\app",
    [string]$RunDirectory = "C:\SEALINK\run",
    [string]$LogDirectory = "C:\SEALINK\logs",
    [ValidateRange(1, 65535)]
    [int]$BackendPort = 8001,
    [ValidateRange(1, 65535)]
    [int]$FrontendPort = 8080
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[SEALINK] $Message" -ForegroundColor Cyan
}

function Test-ListeningPort {
    param([int]$Port)
    return $null -ne (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1)
}

function Stop-CreatedProcess {
    param([Diagnostics.Process]$Process)
    if ($Process -and -not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        $Process.WaitForExit(10000) | Out-Null
    }
}

$principal = [Security.Principal.WindowsPrincipal]::new(
    [Security.Principal.WindowsIdentity]::GetCurrent()
)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Hay chay PowerShell bang Run as administrator."
}

$backendPath = Join-Path $AppPath "backend"
$frontendDist = Join-Path $AppPath "frontend\dist"
$python = Join-Path $backendPath ".venv\Scripts\python.exe"
$backendEnv = Join-Path $backendPath ".env"
foreach ($path in @($python, $backendEnv, (Join-Path $frontendDist "index.html"))) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Thieu runtime file: $path"
    }
}

New-Item -ItemType Directory -Path $RunDirectory, $LogDirectory -Force | Out-Null
$backendStateFile = Join-Path $RunDirectory "backend-test.json"
$frontendStateFile = Join-Path $RunDirectory "frontend-test.json"
foreach ($stateFile in @($backendStateFile, $frontendStateFile)) {
    if (Test-Path -LiteralPath $stateFile -PathType Leaf) {
        $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
        $existing = Get-Process -Id ([int]$state.pid) -ErrorAction SilentlyContinue
        if ($existing -and -not $existing.HasExited) {
            throw "Test process da chay (PID $($state.pid)). Hay dung bang stop_server_test.ps1 truoc."
        }
        Remove-Item -LiteralPath $stateFile -Force
    }
}

foreach ($port in @($BackendPort, $FrontendPort)) {
    if (Test-ListeningPort $port) {
        throw "Port $port dang duoc process khac su dung."
    }
}

$ipv4Addresses = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {
        $_.IPAddress -ne "127.0.0.1" -and
        $_.IPAddress -notlike "169.254.*" -and
        $_.AddressState -eq "Preferred"
    } |
    Select-Object -ExpandProperty IPAddress -Unique)
$testHosts = @("localhost", "127.0.0.1", $env:COMPUTERNAME) + $ipv4Addresses
$testOrigins = @($testHosts | ForEach-Object { "http://${_}:$FrontendPort" } | Select-Object -Unique)
$corsOrigins = $testOrigins -join ","

$firewallRules = @(
    [pscustomobject]@{ Name = "SEALINK-Test-Backend-$BackendPort"; Port = $BackendPort },
    [pscustomobject]@{ Name = "SEALINK-Test-Frontend-$FrontendPort"; Port = $FrontendPort }
)
foreach ($rule in $firewallRules) {
    if (-not (Get-NetFirewallRule -Name $rule.Name -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule `
            -Name $rule.Name `
            -DisplayName $rule.Name `
            -Direction Inbound `
            -Action Allow `
            -Protocol TCP `
            -LocalPort $rule.Port `
            -RemoteAddress LocalSubnet `
            -Profile Any | Out-Null
    }
}

$backendProcess = $null
$frontendProcess = $null
$previousCorsOrigins = if (Test-Path Env:CORS_ORIGINS) { $env:CORS_ORIGINS } else { $null }
$hadPreviousCorsOrigins = Test-Path Env:CORS_ORIGINS

try {
    Write-Step "Khoi dong backend tren 0.0.0.0:$BackendPort"
    $env:CORS_ORIGINS = $corsOrigins
    $backendProcess = Start-Process -FilePath $python `
        -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", [string]$BackendPort) `
        -WorkingDirectory $backendPath `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $LogDirectory "backend-test.stdout.log") `
        -RedirectStandardError (Join-Path $LogDirectory "backend-test.stderr.log") `
        -PassThru

    Write-Step "Khoi dong frontend test tren 0.0.0.0:$FrontendPort"
    $frontendProcess = Start-Process -FilePath $python `
        -ArgumentList @("-m", "http.server", [string]$FrontendPort, "--bind", "0.0.0.0", "--directory", $frontendDist) `
        -WorkingDirectory $frontendDist `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $LogDirectory "frontend-test.stdout.log") `
        -RedirectStandardError (Join-Path $LogDirectory "frontend-test.stderr.log") `
        -PassThru
} catch {
    Stop-CreatedProcess $frontendProcess
    Stop-CreatedProcess $backendProcess
    throw
} finally {
    if ($hadPreviousCorsOrigins) {
        $env:CORS_ORIGINS = $previousCorsOrigins
    } else {
        Remove-Item Env:CORS_ORIGINS -ErrorAction SilentlyContinue
    }
}

try {
    $backendReady = $false
    $frontendReady = $false
    for ($attempt = 1; $attempt -le 30; $attempt++) {
        if ($backendProcess.HasExited -or $frontendProcess.HasExited) { break }
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/health" -Method Get -TimeoutSec 3
            $backendReady = $health.status -eq "ok"
        } catch { $backendReady = $false }
        try {
            $page = Invoke-WebRequest -Uri "http://127.0.0.1:$FrontendPort/" -UseBasicParsing -TimeoutSec 3
            $frontendReady = $page.StatusCode -eq 200
        } catch { $frontendReady = $false }
        if ($backendReady -and $frontendReady) { break }
        Start-Sleep -Seconds 1
    }

    if (-not $backendReady -or -not $frontendReady) {
        $backendError = Get-Content -LiteralPath (Join-Path $LogDirectory "backend-test.stderr.log") -Raw -ErrorAction SilentlyContinue
        $frontendError = Get-Content -LiteralPath (Join-Path $LogDirectory "frontend-test.stderr.log") -Raw -ErrorAction SilentlyContinue
        throw "Test servers khong san sang. Backend=$backendReady Frontend=$frontendReady`nBackend log: $backendError`nFrontend log: $frontendError"
    }

    [IO.File]::WriteAllText(
        $backendStateFile,
        ([pscustomobject]@{ pid = $backendProcess.Id; executable = $python } | ConvertTo-Json),
        [Text.Encoding]::UTF8
    )
    [IO.File]::WriteAllText(
        $frontendStateFile,
        ([pscustomobject]@{ pid = $frontendProcess.Id; executable = $python } | ConvertTo-Json),
        [Text.Encoding]::UTF8
    )
} catch {
    Stop-CreatedProcess $frontendProcess
    Stop-CreatedProcess $backendProcess
    throw
}

Write-Host ""
Write-Host "SEALINK TEST SERVER IS RUNNING" -ForegroundColor Green
Write-Host "Backend PID: $($backendProcess.Id)"
Write-Host "Frontend PID: $($frontendProcess.Id)"
Write-Host "Health: http://127.0.0.1:$BackendPort/health -> ok"
Write-Host "Test URLs:"
$testHosts | Select-Object -Unique | ForEach-Object {
    Write-Host "  http://${_}:$FrontendPort"
}
Write-Host "Firewall access is limited to LocalSubnet."
Write-Host "Run scripts\stop_server_test.ps1 to stop both test processes."
