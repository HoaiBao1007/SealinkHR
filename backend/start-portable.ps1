# ═══════════════════════════════════════════════════════════════════
#  SEALINK Attendance — Portable Startup Script (SQLite)
#  Chạy script này để khởi động backend mà KHÔNG cần Docker.
#  Yêu cầu duy nhất: Python 3.11+ đã cài và có trong PATH.
# ═══════════════════════════════════════════════════════════════════

$ErrorActionPreference = "Stop"

# ── Màu sắc helper ──────────────────────────────────────────────────
function Write-Step  { param($msg) Write-Host "`n▶  $msg" -ForegroundColor Cyan }
function Write-Ok    { param($msg) Write-Host "   ✓  $msg" -ForegroundColor Green }
function Write-Warn  { param($msg) Write-Host "   ⚠  $msg" -ForegroundColor Yellow }
function Write-Fail  { param($msg) Write-Host "   ✗  $msg" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "╔══════════════════════════════════════════════╗" -ForegroundColor Magenta
Write-Host "║   SEALINK Attendance — Portable SQLite Mode  ║" -ForegroundColor Magenta
Write-Host "╚══════════════════════════════════════════════╝" -ForegroundColor Magenta
Write-Host ""

# ── 1. Kiểm tra Python ──────────────────────────────────────────────
Write-Step "Kiểm tra Python..."
try {
    $pythonVersion = python --version 2>&1
    Write-Ok "Tìm thấy: $pythonVersion"
} catch {
    Write-Fail "Không tìm thấy Python! Hãy cài Python 3.11+ và thêm vào PATH."
}

# ── 2. Tạo / Kích hoạt virtual environment ──────────────────────────
Write-Step "Chuẩn bị virtual environment (.venv)..."
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

if (-Not (Test-Path ".venv")) {
    Write-Warn ".venv chưa có, đang tạo..."
    python -m venv .venv
    Write-Ok "Đã tạo .venv"
} else {
    Write-Ok ".venv đã tồn tại"
}

$pip    = ".venv\Scripts\pip.exe"
$python = ".venv\Scripts\python.exe"

# ── 3. Cài dependencies ─────────────────────────────────────────────
Write-Step "Cài đặt dependencies (requirements.txt)..."
& $pip install -r requirements.txt --quiet
Write-Ok "Dependencies đã cài xong"

# ── 4. Tạo file .env nếu chưa có ───────────────────────────────────
Write-Step "Kiểm tra file .env..."
if (-Not (Test-Path ".env")) {
    Write-Warn ".env chưa có, tạo từ .env.sqlite mặc định..."
    Copy-Item ".env.sqlite" ".env"
    Write-Ok "Đã tạo .env (SQLite mode)"
} else {
    # Kiểm tra xem .env đang dùng SQLite hay PostgreSQL
    $dbUrl = Select-String -Path ".env" -Pattern "^DATABASE_URL" | Select-Object -First 1
    if ($dbUrl -and $dbUrl.Line -match "sqlite") {
        Write-Ok ".env hiện tại: SQLite mode"
    } elseif ($dbUrl -and $dbUrl.Line -match "postgresql") {
        Write-Warn ".env hiện tại: PostgreSQL mode (sẽ cần PostgreSQL chạy)"
    } else {
        Write-Ok ".env đã tồn tại (không detect được mode)"
    }
}

# ── 5. Chạy Alembic migrations (tạo/cập nhật schema) ────────────────
Write-Step "Chạy database migrations (alembic upgrade head)..."
try {
    & $python -m alembic upgrade head
    Write-Ok "Schema database đã cập nhật"
} catch {
    Write-Fail "Migration thất bại! Kiểm tra lỗi ở trên."
}

# ── 6. Xác nhận file DB đã tạo (chỉ với SQLite) ─────────────────────
if (Test-Path "sealink_attendance.db") {
    $dbSize = (Get-Item "sealink_attendance.db").Length
    Write-Ok "sealink_attendance.db đã sẵn sàng ($dbSize bytes)"
}

# ── 7. Start uvicorn ────────────────────────────────────────────────
Write-Host ""
Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Magenta
Write-Host "  Backend sẵn sàng! Đang khởi động uvicorn..." -ForegroundColor Green
Write-Host "  API:    http://localhost:8001" -ForegroundColor Green
Write-Host "  Docs:   http://localhost:8001/docs" -ForegroundColor Green
Write-Host "  Health: http://localhost:8001/health" -ForegroundColor Green
Write-Host "  Nhấn Ctrl+C để dừng." -ForegroundColor Gray
Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Magenta
Write-Host ""

& $python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
