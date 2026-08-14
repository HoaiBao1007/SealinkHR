# D:\SEALINK WEB\run-project.ps1
# Unified startup script: choose between XAMPP MySQL, Docker PostgreSQL, or SQLite

function Stop-ProcessUsingPort {
    param([int]$Port)

    $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique

    foreach ($processId in $listeners) {
        if ($processId -and $processId -ne $PID) {
            $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
            if ($process) {
                Write-Host "Stopping process on port ${Port}: $($process.ProcessName) [$processId]" -ForegroundColor Yellow
                Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

function Stop-ProcessesByCommandPattern {
    param([string]$Pattern)

    $processes = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match $Pattern }

    foreach ($process in $processes) {
        if ($process.ProcessId -and $process.ProcessId -ne $PID) {
            Write-Host "Stopping process by pattern '$Pattern': $($process.Name) [$($process.ProcessId)]" -ForegroundColor Yellow
            Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
}

function Start-Frontend {
    Write-Host "Starting Vite Frontend (Port 5174)..." -ForegroundColor Cyan
    Stop-ProcessesByCommandPattern "vite(?:\.js)?|npm\.cmd\s+run\s+dev|start-dev-supervisor"
    Stop-ProcessUsingPort 5174
    $supervisor = Join-Path $PSScriptRoot "frontend\start-dev-supervisor.ps1"
    Start-Process -FilePath "powershell.exe" -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$supervisor`"", "-Port", "5174"
    ) -WorkingDirectory "$PSScriptRoot\frontend" -WindowStyle Hidden -PassThru | Out-Null
    for ($attempt = 1; $attempt -le 15; $attempt++) {
        if (Get-NetTCPConnection -LocalPort 5174 -State Listen -ErrorAction SilentlyContinue) { break }
        Start-Sleep -Seconds 1
    }
    if (Get-NetTCPConnection -LocalPort 5174 -State Listen -ErrorAction SilentlyContinue) {
        Write-Host "-> Frontend supervisor is running at: http://localhost:5174" -ForegroundColor Green
    } else {
        Write-Host "-> Frontend did not start. See frontend\logs\vite-supervisor.log" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "+--------------------------------------------------+" -ForegroundColor Magenta
Write-Host "|       SEALINK Attendance - Startup Menu          |" -ForegroundColor Magenta
Write-Host "+--------------------------------------------------+" -ForegroundColor Magenta
Write-Host ""
Write-Host "  [1] XAMPP MySQL    (recommended - XAMPP installed)" -ForegroundColor Cyan
Write-Host "  [2] Docker PostgreSQL  (original mode - Docker required)" -ForegroundColor Gray
Write-Host "  [3] SQLite portable    (no server needed - fully offline)" -ForegroundColor Green
Write-Host ""
$choice = Read-Host "  Select mode (default: 1)"
if (-not $choice) { $choice = "1" }

# -- MODE 3: SQLite portable ------------------------------------------
if ($choice -eq "3") {
    Write-Host "`n  Launching SQLite portable mode..." -ForegroundColor Green
    Start-Frontend
    Set-Location "$PSScriptRoot\backend"
    & ".\start-portable.ps1"
    exit
}

# -- MODE 1: XAMPP MySQL ----------------------------------------------
if ($choice -eq "1") {
    Write-Host "`n  Launching XAMPP MySQL mode..." -ForegroundColor Cyan
    Start-Frontend
    Set-Location "$PSScriptRoot\backend"
    & ".\start-xampp.ps1"
    exit
}

# -- MODE 2: Docker PostgreSQL (original logic) ------------------------
Write-Host "`n  Launching Docker PostgreSQL mode..." -ForegroundColor Gray
Write-Host "VipSeal - Starting full-stack environment..." -ForegroundColor Cyan

# 1. Start Docker Desktop if not running
$dockerProc = Get-Process "Docker Desktop" -ErrorAction SilentlyContinue
if (-not $dockerProc) {
    Write-Host "Docker Desktop is not running. Starting Docker Desktop..." -ForegroundColor Yellow
    Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    Write-Host "Waiting 10 seconds for Docker daemon to launch..."
    Start-Sleep -Seconds 10
} else {
    Write-Host "Docker Desktop is already running." -ForegroundColor Green
}

# 2. Start PostgreSQL container
Write-Host "Starting PostgreSQL container..." -ForegroundColor Cyan
Set-Location "$PSScriptRoot"
docker compose up -d db

Write-Host "Waiting 5 seconds for PostgreSQL port 5432..."
Start-Sleep -Seconds 5

# 3. Bootstrap & Migrate Database
Write-Host "Bootstrapping database schema & running alembic migrations..." -ForegroundColor Cyan
Set-Location "$PSScriptRoot\backend"
.\.venv\Scripts\python.exe -c "from app.db.base import Base; from app.db.session import engine; import app.models; Base.metadata.create_all(bind=engine)"
.\.venv\Scripts\python.exe -m alembic upgrade head

# 4. Start Backend
Write-Host "Starting FastAPI Backend (Port 8001)..." -ForegroundColor Cyan
Stop-ProcessesByCommandPattern "uvicorn\s+app\.main:app"
Stop-ProcessUsingPort 8001
Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "-m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload --reload-dir app" -NoNewWindow -PassThru | Out-Null

# 5. Start Frontend
Start-Frontend

Write-Host "`nEnvironment is up!" -ForegroundColor Green
Write-Host "-> Frontend: http://localhost:5174"
Write-Host "-> Backend:  http://localhost:8001"
Write-Host "`nPress Ctrl+C to exit. Note that the processes are running in this window session."
