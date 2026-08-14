# ===================================================================
#  SEALINK Attendance - XAMPP MySQL Startup Script
#  Runs backend with MySQL/MariaDB provided by XAMPP.
#  Requirement: XAMPP installed (default: C:\xampp)
# ===================================================================

$ErrorActionPreference = "Stop"

function Write-Step  { param($msg) Write-Host "`n>>> $msg" -ForegroundColor Cyan }
function Write-Ok    { param($msg) Write-Host "   [OK] $msg" -ForegroundColor Green }
function Write-Warn  { param($msg) Write-Host "   [WARN] $msg" -ForegroundColor Yellow }
function Write-Fail  { param($msg) Write-Host "   [FAIL] $msg" -ForegroundColor Red; exit 1 }

function Stop-BackendOnPort {
    param([int]$Port)
    $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($processId in $listeners) {
        if ($processId -and $processId -ne $PID) {
            $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
            if ($process -and $process.ProcessName -in @('python', 'python3', 'uvicorn')) {
                Write-Warn "Stopping existing backend on port ${Port}: $($process.ProcessName) [$processId]"
                Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host ""
Write-Host "+----------------------------------------------+" -ForegroundColor Magenta
Write-Host "|   SEALINK Attendance - XAMPP MySQL Mode      |" -ForegroundColor Magenta
Write-Host "+----------------------------------------------+" -ForegroundColor Magenta

# ── 1. Detect XAMPP Installation ────────────────────────────────────
Write-Step "Detecting XAMPP installation..."

$xamppPaths = @(
    "C:\xampp",
    "D:\xampp",
    "C:\Program Files\xampp",
    "$env:SystemDrive\xampp"
)
$xamppRoot = $null
foreach ($p in $xamppPaths) {
    if (Test-Path "$p\mysql\bin\mysql.exe") {
        $xamppRoot = $p
        break
    }
}

if (-not $xamppRoot) {
    Write-Fail "XAMPP not found! Please install XAMPP first: https://www.apachefriends.org/download.html`n   Then run this script again."
}
Write-Ok "XAMPP found at: $xamppRoot"

$mysqlExe   = "$xamppRoot\mysql\bin\mysql.exe"
$mysqlAdmin = "$xamppRoot\mysql\bin\mysqladmin.exe"
$mysqld     = "$xamppRoot\mysql\bin\mysqld.exe"

# ── 2. Check / Start MySQL ───────────────────────────────────────────
Write-Step "Checking MySQL status (port 3306)..."

$mysqlRunning = $false
$socket = New-Object System.Net.Sockets.TcpClient
try {
    $socket.Connect("127.0.0.1", 3306)
    if ($socket.Connected) {
        $mysqlRunning = $true
        $socket.Close()
    }
} catch {}

if (-not $mysqlRunning) {
    Write-Warn "MySQL is not running. Attempting to start..."
    Write-Host "   Starting mysqld directly..." -ForegroundColor Yellow
    $mysqldataPath = "$xamppRoot\mysql\data"
    Start-Process -FilePath $mysqld -ArgumentList "--defaults-file=`"$xamppRoot\mysql\bin\my.ini`"", "--standalone" -WindowStyle Hidden
    Write-Host "   Waiting up to 15 seconds for MySQL to start..." -ForegroundColor Gray
    for ($i = 1; $i -le 15; $i++) {
        Start-Sleep -Seconds 1
        $socket = New-Object System.Net.Sockets.TcpClient
        try {
            $socket.Connect("127.0.0.1", 3306)
            if ($socket.Connected) {
                $mysqlRunning = $true
                $socket.Close()
                break
            }
        } catch {}
    }

    if (-not $mysqlRunning) {
        Write-Fail "Could not start MySQL on port 3306. Please check logs or start XAMPP MySQL manually."
    }
}
Write-Ok "MySQL is running on port 3306"

# ── 3. Create database 'sealink_payroll_db' if not exists ───────────────────
Write-Step "Ensuring database 'sealink_payroll_db' exists..."

# Parse connection info from .env.xampp or current .env
$dbUrl = "mysql+pymysql://root:@localhost:3306/sealink_payroll_db?charset=utf8mb4"
$dbName = "sealink_payroll_db"
if (Test-Path ".env") {
    $envContent = Get-Content ".env" | Where-Object { $_ -match "^DATABASE_URL" } | Select-Object -First 1
    if ($envContent -match "^DATABASE_URL\s*=\s*(.*)") {
        $dbUrl = $Matches[1].Trim()
        Write-Ok "Using DATABASE_URL from .env"
    }
}

if ($dbUrl -match 'mysql\+pymysql://[^/]+/([^?#\s]+)') {
    $dbName = $Matches[1]
}

# ── 3. Create database if not exists ───────────────────
Write-Step "Ensuring database '$dbName' exists..."

$createDbSql = "CREATE DATABASE IF NOT EXISTS ``$dbName`` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
try {
    & $mysqlExe -u root --execute=$createDbSql 2>&1 | Out-Null
    Write-Ok "Database '$dbName' is ready"
} catch {
    Write-Warn "Could not auto-create database (may already exist or require password)"
    Write-Host "   Trying without password check..." -ForegroundColor Gray
}


# ── 4. Setup .env ────────────────────────────────────────────────────
Write-Step "Setting up .env configuration..."
if (-not (Test-Path ".env")) {
    Copy-Item ".env.xampp" ".env"
    Write-Ok "Created .env from .env.xampp (XAMPP MySQL mode)"
} else {
    $currentUrl = (Get-Content ".env" | Where-Object { $_ -match "^DATABASE_URL" } | Select-Object -First 1)
    if ($currentUrl -match "mysql") {
        Write-Ok ".env is already configured for MySQL"
    } else {
        Write-Warn ".env exists but is not MySQL mode. Backing up and switching..."
        Copy-Item ".env" ".env.backup.$(Get-Date -Format 'yyyyMMdd_HHmmss')"
        Copy-Item ".env.xampp" ".env"
        Write-Ok "Switched .env to XAMPP MySQL mode (backup saved)"
    }
}

# ── 5. Setup virtual environment ─────────────────────────────────────
Write-Step "Setting up Python virtual environment..."
if (-not (Test-Path ".venv")) {
    Write-Warn ".venv not found, creating..."
    python -m venv .venv
}
$pip    = ".venv\Scripts\pip.exe"
$python = ".venv\Scripts\python.exe"

# ── 6. Install dependencies ──────────────────────────────────────────
Write-Step "Installing dependencies (including PyMySQL)..."
& $pip install -r requirements.txt --quiet
Write-Ok "All dependencies installed"

# ── 7. Run Alembic migrations ────────────────────────────────────────
Write-Step "Running database migrations..."
try {
    & $python -m alembic upgrade head
    Write-Ok "Database schema is up to date"
} catch {
    Write-Fail "Migration failed! Check error above."
}

# ── 7.5 Run seed script for admin_sealink ────────────────────────────
Write-Step "Running seeding script (admin_sealink)..."
try {
    & $python -m app.db.seed_sealink_admin
    Write-Ok "Seeding admin_sealink user completed"
} catch {
    Write-Fail "Seeding failed! Check error above."
}

# ── 8. Verify DB tables ──────────────────────────────────────────────
Write-Step "Verifying database tables..."
$verifyScript = @"
import pymysql, sys
try:
    conn = pymysql.connect(host='localhost', user='root', password='', database='$dbName', charset='utf8mb4')
    cur = conn.cursor()
    cur.execute("SHOW TABLES")
    tables = [r[0] for r in cur.fetchall()]
    print(f'Tables ({len(tables)}): ' + ', '.join(tables))
    conn.close()
    sys.exit(0)
except Exception as e:
    print(f'ERROR: {e}')
    sys.exit(1)
"@

$tempFile = Join-Path $env:TEMP "verify_db.py"
$verifyScript | Out-File -FilePath $tempFile -Encoding utf8
try {
    & $python $tempFile
} finally {
    if (Test-Path $tempFile) { Remove-Item $tempFile }
}

# ── 9. Start uvicorn ─────────────────────────────────────────────────
Write-Host ""
Write-Host "===================================================" -ForegroundColor Magenta
Write-Host "  XAMPP MySQL mode ready! Starting backend..." -ForegroundColor Green
Write-Host "  API:      http://localhost:8001" -ForegroundColor Green
Write-Host "  Docs:     http://localhost:8001/docs" -ForegroundColor Green
Write-Host "  Health:   http://localhost:8001/health" -ForegroundColor Green
Write-Host "  phpMyAdmin: http://localhost/phpmyadmin" -ForegroundColor Cyan
Write-Host "  Press Ctrl+C to stop." -ForegroundColor Gray
Write-Host "===================================================" -ForegroundColor Magenta
Write-Host "" 

Stop-BackendOnPort -Port 8001
& $python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
