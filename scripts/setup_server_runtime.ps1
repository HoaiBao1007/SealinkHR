[CmdletBinding()]
param(
    [string]$AppPath = "C:\SEALINK\app",
    [string]$UploadsPath = "C:\SEALINK\data\uploads",
    [string]$LogDirectory = "C:\SEALINK\logs",
    [string]$HealthUrl = "http://127.0.0.1:8001/health",
    [ValidateRange(1, 65535)]
    [int]$BackendPort = 8001,
    [switch]$SkipFrontendBuild
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[SEALINK] $Message" -ForegroundColor Cyan
}

function Invoke-Checked {
    param(
        [string]$Executable,
        [string[]]$Arguments,
        [string]$Description
    )
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Description that bai (exit code $LASTEXITCODE)."
    }
}

function Resolve-Python312OrNewer {
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        $candidate = (& $launcher.Source -3.12 -c "import sys; print(sys.executable)" 2>$null | Select-Object -Last 1)
        if ($LASTEXITCODE -eq 0 -and $candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    foreach ($name in @("python.exe", "python3.exe")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $command) { continue }
        $versionText = (& $command.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null | Select-Object -Last 1)
        if ($LASTEXITCODE -eq 0 -and $versionText -match "^(\d+)\.(\d+)$") {
            if ([int]$Matches[1] -eq 3 -and [int]$Matches[2] -ge 12) {
                return $command.Source
            }
        }
    }
    return $null
}

function Get-TreeStats {
    param([string]$Path)
    $files = @(Get-ChildItem -LiteralPath $Path -Recurse -File -Force)
    $bytes = ($files | Measure-Object -Property Length -Sum).Sum
    if ($null -eq $bytes) { $bytes = 0L }
    return [pscustomobject]@{ Files = $files.Count; Bytes = [long]$bytes }
}

$backendPath = Join-Path $AppPath "backend"
$frontendPath = Join-Path $AppPath "frontend"
$requirements = Join-Path $backendPath "requirements.txt"
$backendEnv = Join-Path $backendPath ".env"
$backendUploads = Join-Path $backendPath "uploads"
$venvPath = Join-Path $backendPath ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"

foreach ($requiredPath in @($backendPath, $requirements, $backendEnv, $backendUploads, $UploadsPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Thieu duong dan bat buoc: $requiredPath"
    }
}

$uploadsItem = Get-Item -LiteralPath $backendUploads -Force
if (($uploadsItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) {
    throw "backend\uploads khong phai junction."
}
$junctionTarget = [string]$uploadsItem.Target
if ([IO.Path]::GetFullPath($junctionTarget) -ne [IO.Path]::GetFullPath($UploadsPath)) {
    throw "Junction uploads tro sai dich: $junctionTarget"
}
$uploadStats = Get-TreeStats $UploadsPath
if ($uploadStats.Files -ne 5 -or $uploadStats.Bytes -ne 1825545L) {
    throw "Uploads khong khop backup: Files=$($uploadStats.Files), Bytes=$($uploadStats.Bytes)"
}

$basePython = Resolve-Python312OrNewer
if (-not $basePython) {
    throw "Khong tim thay Python 3.12+. Hay cai Python 3.12 x64 cho Windows va bat py launcher."
}
Write-Step "Python: $basePython"

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    Write-Step "Tao Python virtual environment"
    Invoke-Checked -Executable $basePython `
        -Arguments @("-m", "venv", $venvPath) `
        -Description "Tao virtual environment"
}

Write-Step "Cap nhat pip va cai backend dependencies"
Invoke-Checked -Executable $venvPython `
    -Arguments @("-m", "pip", "install", "--upgrade", "pip") `
    -Description "Cap nhat pip"
Invoke-Checked -Executable $venvPython `
    -Arguments @("-m", "pip", "install", "--requirement", $requirements) `
    -Description "Cai backend dependencies"

Push-Location $backendPath
try {
    Write-Step "Chay Alembic upgrade head"
    Invoke-Checked -Executable $venvPython `
        -Arguments @("-m", "alembic", "upgrade", "head") `
        -Description "Alembic upgrade"

    Write-Step "Doi soat database bang tai khoan ung dung trong .env"
    Invoke-Checked -Executable $venvPython `
        -Arguments @("-m", "app.db.verify_runtime") `
        -Description "Doi soat database"
} finally {
    Pop-Location
}

if (-not $SkipFrontendBuild) {
    if (-not (Test-Path -LiteralPath $frontendPath -PathType Container)) {
        throw "Khong tim thay frontend path: $frontendPath"
    }
    $node = Get-Command node.exe -ErrorAction SilentlyContinue
    $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $node -or -not $npm) {
        throw "Khong tim thay Node.js/npm. Hay cai Node.js LTS x64."
    }
    $nodeVersion = (& $node.Source --version).TrimStart("v")
    Write-Step "Node.js: $nodeVersion"

    Push-Location $frontendPath
    try {
        Write-Step "Cai frontend dependencies bang npm ci"
        Invoke-Checked -Executable $npm.Source `
            -Arguments @("ci", "--no-audit", "--no-fund") `
            -Description "npm ci"
        Write-Step "Build frontend production"
        Invoke-Checked -Executable $npm.Source `
            -Arguments @("run", "build") `
            -Description "Frontend build"
    } finally {
        Pop-Location
    }
    if (-not (Test-Path -LiteralPath (Join-Path $frontendPath "dist\index.html") -PathType Leaf)) {
        throw "Frontend build khong tao dist\index.html."
    }
}

New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
$stdoutLog = Join-Path $LogDirectory "runtime_check.stdout.log"
$stderrLog = Join-Path $LogDirectory "runtime_check.stderr.log"

try {
    $existingHealth = Invoke-RestMethod -Uri $HealthUrl -Method Get -TimeoutSec 3
    if ($existingHealth.status -eq "ok") {
        throw "Port $BackendPort da co API dang chay; khong the xac minh day la process moi."
    }
} catch [System.Net.WebException] {
    # Expected before the temporary Uvicorn process starts.
} catch [System.Net.Http.HttpRequestException] {
    # Expected in newer PowerShell versions.
}

Write-Step "Khoi dong Uvicorn tam thoi va kiem tra health"
$uvicornProcess = Start-Process -FilePath $venvPython `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", [string]$BackendPort) `
    -WorkingDirectory $backendPath `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru

$healthPassed = $false
try {
    for ($attempt = 1; $attempt -le 30; $attempt++) {
        if ($uvicornProcess.HasExited) { break }
        try {
            $health = Invoke-RestMethod -Uri $HealthUrl -Method Get -TimeoutSec 3
            if ($health.status -eq "ok") {
                $healthPassed = $true
                break
            }
        } catch {
            Start-Sleep -Seconds 1
        }
    }

    if (-not $healthPassed) {
        $errorText = if (Test-Path -LiteralPath $stderrLog) {
            Get-Content -LiteralPath $stderrLog -Raw -ErrorAction SilentlyContinue
        } else { "" }
        throw "Backend health check that bai. Log: $errorText"
    }
} finally {
    if (-not $uvicornProcess.HasExited) {
        Stop-Process -Id $uvicornProcess.Id -Force -ErrorAction SilentlyContinue
        $uvicornProcess.WaitForExit(10000) | Out-Null
    }
    $uvicornProcess.Dispose()
}

Write-Host ""
Write-Host "SERVER RUNTIME SETUP COMPLETE" -ForegroundColor Green
Write-Host "Backend venv: $venvPath"
Write-Host "Database: employees=59, attendance_daily=1857, timesheets=121"
Write-Host "Uploads: files=$($uploadStats.Files), bytes=$($uploadStats.Bytes)"
if (-not $SkipFrontendBuild) { Write-Host "Frontend: $frontendPath\dist" }
Write-Host "Health: $HealthUrl -> ok"
Write-Host "Temporary Uvicorn process was stopped; no unmanaged server was left running."
