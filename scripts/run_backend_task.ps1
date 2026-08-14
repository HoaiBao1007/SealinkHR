[CmdletBinding()]
param(
    [string]$AppPath = "C:\SEALINK\app",
    [string]$LogDirectory = "C:\SEALINK\logs",
    [ValidateRange(1, 65535)]
    [int]$BackendPort = 8001
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
$stdoutLog = Join-Path $LogDirectory "backend-service.stdout.log"
$stderrLog = Join-Path $LogDirectory "backend-service.stderr.log"
$bootstrapLog = Join-Path $LogDirectory "backend-service.bootstrap.log"
$exitCode = 1
$locationPushed = $false

function Write-BootstrapLog {
    param([string]$Message)
    Add-Content -LiteralPath $bootstrapLog -Value "[$(Get-Date -Format o)] $Message"
}

try {
    Write-BootstrapLog "Runner started; identity=$([Security.Principal.WindowsIdentity]::GetCurrent().Name); pid=$PID; PowerShell=$($PSVersionTable.PSVersion)"

    $backendPath = Join-Path $AppPath "backend"
    $python = Join-Path $backendPath ".venv\Scripts\python.exe"
    $backendEnv = Join-Path $backendPath ".env"
    foreach ($path in @($backendPath, $python, $backendEnv)) {
        if (-not (Test-Path -LiteralPath $path)) {
            throw "Missing backend runtime path: $path"
        }
    }

    $pythonVersion = (& $python --version 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Python runtime check failed with exit code $LASTEXITCODE."
    }
    Write-BootstrapLog "Runtime paths verified; backend=$backendPath; python=$pythonVersion; port=$BackendPort"

    Add-Content -LiteralPath $stdoutLog -Value "[$(Get-Date -Format o)] Starting SEALINK backend on port $BackendPort"
    Push-Location $backendPath
    $locationPushed = $true
    # Windows PowerShell 5.1 turns native stderr (including harmless Python
    # warnings) into error records. Do not let those records terminate the task.
    $savedErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $python -m uvicorn app.main:app --host 0.0.0.0 --port $BackendPort 1>> $stdoutLog 2>> $stderrLog
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $savedErrorActionPreference
    }
    Write-BootstrapLog "Uvicorn exited with code $exitCode"
} catch {
    $details = "Runner failed: $($_.Exception.Message)"
    if ($_.ScriptStackTrace) {
        $details += [Environment]::NewLine + $_.ScriptStackTrace
    }
    try {
        Write-BootstrapLog $details
        Add-Content -LiteralPath $stderrLog -Value "[$(Get-Date -Format o)] $details"
    } catch {
        # Task Scheduler will still retain the non-zero exit code if logging itself fails.
    }
} finally {
    if ($locationPushed) {
        Pop-Location
    }
}

exit $exitCode
