[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$DatabaseUser,

    [string]$DatabaseHost = "127.0.0.1",

    [ValidateRange(1, 65535)]
    [int]$DatabasePort = 3306,

    [ValidatePattern("^[A-Za-z0-9_]+$")]
    [string]$DatabaseName = "sealink_hr",

    [string]$PackageDirectory = "D:\SEALINK\backups\incoming",

    [string]$DatabaseBackupName = "sealink_20260814_102648.sql.gz",

    [string]$UploadsArchiveName = "sealink_transfer_20260814_102648_uploads.zip",

    [string]$ExpectedDatabaseSha256 = "396aefdc79bd88329ce7bc614446ca37ec41db5474691c27887fb70037c7f8cf",

    [string]$ExpectedUploadsSha256 = "4497d82f6b8ad84a493694baf24e49b1684781ed0aa51ad33bcdcbb1cd477c08",

    [string]$UploadsPath = "D:\SEALINK\data\uploads",

    [string]$BackendPath = "D:\SEALINK\app\backend",

    [string]$SafetyBackupRoot = "D:\SEALINK\backups\pre_restore",

    [string]$WorkRoot = "D:\SEALINK\backups\restore_work",

    [string]$MariaDbBinDirectory = "",

    [string]$BackendServiceName = "",

    [string]$HealthUrl = "http://127.0.0.1:8001/health",

    [switch]$SkipHealthCheck,

    [Parameter(Mandatory = $true)]
    [switch]$ConfirmRestore
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[SEALINK] $Message" -ForegroundColor Cyan
}

function Get-Sha256 {
    param([string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-TreeStats {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        return [pscustomobject]@{ Files = 0; Bytes = 0L }
    }
    $files = @(Get-ChildItem -LiteralPath $Path -Recurse -File -Force)
    $bytes = ($files | Measure-Object -Property Length -Sum).Sum
    if ($null -eq $bytes) { $bytes = 0L }
    return [pscustomobject]@{ Files = $files.Count; Bytes = [long]$bytes }
}

function Resolve-MariaDbTool {
    param(
        [string[]]$Names,
        [string]$ExplicitBinDirectory
    )

    if ($ExplicitBinDirectory) {
        foreach ($name in $Names) {
            $candidate = Join-Path $ExplicitBinDirectory $name
            if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                return (Resolve-Path -LiteralPath $candidate).Path
            }
        }
    }

    foreach ($name in $Names) {
        $command = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($command) { return $command.Source }
    }

    $searchPatterns = @(
        "C:\Program Files\MariaDB *\bin\*",
        "C:\Program Files\MySQL\MySQL Server *\bin\*",
        "C:\xampp\mysql\bin\*"
    )
    foreach ($pattern in $searchPatterns) {
        foreach ($name in $Names) {
            $match = Get-ChildItem -Path $pattern -File -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -ieq $name } |
                Select-Object -First 1
            if ($match) { return $match.FullName }
        }
    }

    throw "Khong tim thay cong cu MariaDB: $($Names -join ', ')."
}

function Invoke-DatabaseClient {
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

function Backup-CurrentDatabase {
    param(
        [string]$DumpExecutable,
        [string]$Destination,
        [string]$ErrorFile
    )

    $arguments = @(
        "--single-transaction",
        "--routines",
        "--triggers",
        "--events",
        "--hex-blob",
        "--default-character-set=utf8mb4",
        "-h", $DatabaseHost,
        "-P", [string]$DatabasePort,
        "-u", $DatabaseUser,
        $DatabaseName
    )

    $process = Start-Process -FilePath $DumpExecutable `
        -ArgumentList $arguments `
        -NoNewWindow `
        -Wait `
        -PassThru `
        -RedirectStandardOutput $Destination `
        -RedirectStandardError $ErrorFile

    if ($process.ExitCode -ne 0) {
        $errorText = if (Test-Path -LiteralPath $ErrorFile) {
            (Get-Content -LiteralPath $ErrorFile -Raw -ErrorAction SilentlyContinue)
        } else { "" }
        throw "Backup database hien tai that bai: $errorText"
    }
    if (-not (Test-Path -LiteralPath $Destination) -or (Get-Item -LiteralPath $Destination).Length -lt 128) {
        throw "Backup database hien tai rong hoac khong hop le."
    }
}

function Restore-DatabaseFromSql {
    param(
        [string]$ClientExecutable,
        [string[]]$Arguments,
        [string]$SourceSql,
        [string]$ErrorFile
    )

    $process = Start-Process -FilePath $ClientExecutable `
        -ArgumentList $Arguments `
        -NoNewWindow `
        -Wait `
        -PassThru `
        -RedirectStandardInput $SourceSql `
        -RedirectStandardError $ErrorFile

    if ($process.ExitCode -ne 0) {
        $errorText = if (Test-Path -LiteralPath $ErrorFile) {
            (Get-Content -LiteralPath $ErrorFile -Raw -ErrorAction SilentlyContinue)
        } else { "" }
        throw "Restore database that bai (exit code $($process.ExitCode)): $errorText"
    }
}

function Assert-SafeDirectoryTarget {
    param(
        [string]$Path,
        [string]$Description
    )

    $fullPath = [System.IO.Path]::GetFullPath($Path)
    $pathRoot = [System.IO.Path]::GetPathRoot($fullPath)
    if ($fullPath.TrimEnd("\") -eq $pathRoot.TrimEnd("\")) {
        throw "$Description khong duoc la goc o dia: $fullPath"
    }
}

if (-not $ConfirmRestore) {
    throw "Phai truyen -ConfirmRestore de cho phep thao tac thay the database va uploads."
}

if ($PackageDirectory.StartsWith("\\")) {
    throw "Khong restore truc tiep tu SMB. Hay copy goi vao o dia local: D:\SEALINK\backups\incoming."
}

Assert-SafeDirectoryTarget -Path $UploadsPath -Description "UploadsPath"
Assert-SafeDirectoryTarget -Path $BackendPath -Description "BackendPath"
Assert-SafeDirectoryTarget -Path $SafetyBackupRoot -Description "SafetyBackupRoot"
Assert-SafeDirectoryTarget -Path $WorkRoot -Description "WorkRoot"

$databasePackage = Join-Path $PackageDirectory $DatabaseBackupName
$uploadsPackage = Join-Path $PackageDirectory $UploadsArchiveName
foreach ($package in @($databasePackage, $uploadsPackage)) {
    if (-not (Test-Path -LiteralPath $package -PathType Leaf)) {
        throw "Khong tim thay goi restore tren o dia server: $package"
    }
}

Write-Step "Kiem tra checksum goi restore"
$databaseHash = Get-Sha256 $databasePackage
$uploadsHash = Get-Sha256 $uploadsPackage
if ($databaseHash -ne $ExpectedDatabaseSha256.ToLowerInvariant()) {
    throw "Checksum database khong khop. Expected=$ExpectedDatabaseSha256 Actual=$databaseHash"
}
if ($uploadsHash -ne $ExpectedUploadsSha256.ToLowerInvariant()) {
    throw "Checksum uploads khong khop. Expected=$ExpectedUploadsSha256 Actual=$uploadsHash"
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$workDirectory = Join-Path $WorkRoot $timestamp
$safetyDirectory = Join-Path $SafetyBackupRoot $timestamp
$restoreSql = Join-Path $workDirectory "restore_source.sql"
$extractedUploads = Join-Path $workDirectory "uploads_extracted"
New-Item -ItemType Directory -Path $workDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $safetyDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $extractedUploads -Force | Out-Null

Write-Step "Giai nen va kiem tra database dump tren o dia local"
$sourceStream = [System.IO.File]::OpenRead($databasePackage)
try {
    $gzipStream = [System.IO.Compression.GzipStream]::new(
        $sourceStream,
        [System.IO.Compression.CompressionMode]::Decompress
    )
    try {
        $sqlStream = [System.IO.File]::Create($restoreSql)
        try { $gzipStream.CopyTo($sqlStream) }
        finally { $sqlStream.Dispose() }
    }
    finally { $gzipStream.Dispose() }
}
finally { $sourceStream.Dispose() }
if ((Get-Item -LiteralPath $restoreSql).Length -lt 128) {
    throw "Database dump sau khi giai nen khong hop le."
}

Write-Step "Giai nen va kiem tra uploads trong thu muc tam"
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($uploadsPackage)
try {
    $expectedUploadEntries = @($zip.Entries | Where-Object { -not $_.FullName.EndsWith("/") })
    $expectedUploadFiles = $expectedUploadEntries.Count
    $expectedUploadBytes = ($expectedUploadEntries | Measure-Object -Property Length -Sum).Sum
    if ($null -eq $expectedUploadBytes) { $expectedUploadBytes = 0L }

    $extractRoot = [System.IO.Path]::GetFullPath($extractedUploads).TrimEnd("\") + "\"
    foreach ($entry in $zip.Entries) {
        $candidate = [System.IO.Path]::GetFullPath((Join-Path $extractedUploads $entry.FullName))
        if (-not $candidate.StartsWith($extractRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Uploads archive chua duong dan khong an toan: $($entry.FullName)"
        }
    }
}
finally { $zip.Dispose() }
[System.IO.Compression.ZipFile]::ExtractToDirectory($uploadsPackage, $extractedUploads)
$extractedStats = Get-TreeStats $extractedUploads
if ($extractedStats.Files -ne $expectedUploadFiles -or $extractedStats.Bytes -ne [long]$expectedUploadBytes) {
    throw "Uploads sau giai nen khong khop archive."
}

$databaseClient = Resolve-MariaDbTool -Names @("mariadb.exe", "mysql.exe") -ExplicitBinDirectory $MariaDbBinDirectory
$databaseDump = Resolve-MariaDbTool -Names @("mariadb-dump.exe", "mysqldump.exe") -ExplicitBinDirectory $MariaDbBinDirectory
Write-Step "MariaDB client: $databaseClient"
Write-Step "MariaDB dump: $databaseDump"

$typedConfirmation = Read-Host "Nhap chinh xac 'RESTORE $DatabaseName' de tiep tuc"
if ($typedConfirmation -cne "RESTORE $DatabaseName") {
    throw "Da huy restore do chuoi xac nhan khong khop."
}

$securePassword = Read-Host "Nhap mat khau MariaDB cho user $DatabaseUser" -AsSecureString
$passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
$databasePassword = ""
$hadPreviousMysqlPassword = Test-Path Env:MYSQL_PWD
$previousMysqlPassword = if ($hadPreviousMysqlPassword) { $env:MYSQL_PWD } else { $null }
$serviceWasRunning = $false
$restoreSucceeded = $false

try {
    $databasePassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
    $env:MYSQL_PWD = $databasePassword

    $baseClientArguments = @(
        "--host=$DatabaseHost",
        "--port=$DatabasePort",
        "--user=$DatabaseUser",
        "--default-character-set=utf8mb4",
        "--batch",
        "--skip-column-names"
    )

    Write-Step "Kiem tra ket noi MariaDB va quyen tren server"
    Invoke-DatabaseClient -Executable $databaseClient `
        -Arguments ($baseClientArguments + @("--execute=SELECT VERSION();")) `
        -Description "Ket noi MariaDB"

    if ($BackendServiceName) {
        $service = Get-Service -Name $BackendServiceName -ErrorAction Stop
        $serviceWasRunning = $service.Status -eq "Running"
        if ($serviceWasRunning) {
            Write-Step "Dung Windows Service $BackendServiceName"
            Stop-Service -Name $BackendServiceName -Force -ErrorAction Stop
            (Get-Service -Name $BackendServiceName).WaitForStatus("Stopped", [TimeSpan]::FromSeconds(30))
        }
    }

    $databaseExistsResult = & $databaseClient @baseClientArguments `
        "--execute=SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='$DatabaseName';"
    if ($LASTEXITCODE -ne 0) { throw "Khong kiem tra duoc database hien tai." }
    $databaseExists = [int](($databaseExistsResult | Select-Object -Last 1).ToString().Trim()) -gt 0

    if ($databaseExists) {
        Write-Step "Backup database $DatabaseName hien tai truoc restore"
        $currentDatabaseBackup = Join-Path $safetyDirectory "${DatabaseName}_before_restore.sql"
        $currentDatabaseError = Join-Path $safetyDirectory "${DatabaseName}_before_restore.stderr.txt"
        Backup-CurrentDatabase -DumpExecutable $databaseDump `
            -Destination $currentDatabaseBackup `
            -ErrorFile $currentDatabaseError
        $currentDatabaseHash = Get-Sha256 $currentDatabaseBackup
        [System.IO.File]::WriteAllText(
            "$currentDatabaseBackup.sha256",
            $currentDatabaseHash,
            [System.Text.Encoding]::ASCII
        )
    } else {
        Write-Warning "Database $DatabaseName chua ton tai; khong co database cu de backup."
    }

    if (Test-Path -LiteralPath $UploadsPath -PathType Container) {
        Write-Step "Di chuyen uploads hien tai vao safety backup"
        $previousUploads = Join-Path $safetyDirectory "uploads_before_restore"
        Move-Item -LiteralPath $UploadsPath -Destination $previousUploads -ErrorAction Stop
    }

    Write-Step "Tao lai database $DatabaseName"
    $replaceDatabaseSql = "DROP DATABASE IF EXISTS $DatabaseName; CREATE DATABASE $DatabaseName CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
    Invoke-DatabaseClient -Executable $databaseClient `
        -Arguments ($baseClientArguments + @("--execute=$replaceDatabaseSql")) `
        -Description "Tao lai database"

    Write-Step "Restore SQL vao $DatabaseName"
    $restoreError = Join-Path $safetyDirectory "restore.stderr.txt"
    Restore-DatabaseFromSql -ClientExecutable $databaseClient `
        -Arguments ($baseClientArguments + @($DatabaseName)) `
        -SourceSql $restoreSql `
        -ErrorFile $restoreError

    Write-Step "Khoi phuc uploads vao $UploadsPath"
    New-Item -ItemType Directory -Path $UploadsPath -Force | Out-Null
    $robocopyOutput = & robocopy.exe $extractedUploads $UploadsPath /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /XJ
    $robocopyExitCode = $LASTEXITCODE
    $robocopyOutput | Write-Verbose
    if ($robocopyExitCode -gt 7) {
        throw "Copy uploads that bai (robocopy exit code $robocopyExitCode)."
    }
    $restoredUploadStats = Get-TreeStats $UploadsPath
    if ($restoredUploadStats.Files -ne $expectedUploadFiles -or $restoredUploadStats.Bytes -ne [long]$expectedUploadBytes) {
        throw "Uploads sau restore khong khop goi nguon."
    }

    Write-Step "Tao hoac kiem tra junction backend\uploads"
    $backendUploadsPath = Join-Path $BackendPath "uploads"
    if (-not (Test-Path -LiteralPath $BackendPath -PathType Container)) {
        throw "Khong tim thay backend path: $BackendPath"
    }
    $backendUploadsItem = Get-Item -LiteralPath $backendUploadsPath -Force -ErrorAction SilentlyContinue
    if ($null -ne $backendUploadsItem) {
        if (($backendUploadsItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            $currentTarget = [string]$backendUploadsItem.Target
            if ([System.IO.Path]::GetFullPath($currentTarget) -ne [System.IO.Path]::GetFullPath($UploadsPath)) {
                throw "Junction backend\uploads dang tro sai dich: $currentTarget"
            }
        } else {
            $preservedBackendUploads = Join-Path $safetyDirectory "backend_uploads_before_junction"
            Move-Item -LiteralPath $backendUploadsPath -Destination $preservedBackendUploads -ErrorAction Stop
            New-Item -ItemType Junction -Path $backendUploadsPath -Target $UploadsPath | Out-Null
        }
    } else {
        New-Item -ItemType Junction -Path $backendUploadsPath -Target $UploadsPath | Out-Null
    }

    Write-Step "Kiem tra database sau restore"
    $tableCountResult = & $databaseClient @baseClientArguments `
        "--execute=SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='$DatabaseName' AND TABLE_TYPE='BASE TABLE';"
    if ($LASTEXITCODE -ne 0) { throw "Khong dem duoc bang sau restore." }
    $tableCount = [int](($tableCountResult | Select-Object -Last 1).ToString().Trim())
    if ($tableCount -lt 1) { throw "Database sau restore khong co bang." }

    $keyCounts = & $databaseClient @baseClientArguments $DatabaseName `
        "--execute=SELECT 'employees',COUNT(*) FROM employees UNION ALL SELECT 'attendance_daily',COUNT(*) FROM attendance_daily UNION ALL SELECT 'timesheets',COUNT(*) FROM timesheets UNION ALL SELECT 'alembic_version',COUNT(*) FROM alembic_version;"
    if ($LASTEXITCODE -ne 0) { throw "Kiem tra cac bang chinh that bai." }

    $junction = Get-Item -LiteralPath (Join-Path $BackendPath "uploads") -Force
    if (($junction.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -eq 0) {
        throw "backend\uploads khong phai junction sau restore."
    }

    if ($BackendServiceName -and $serviceWasRunning) {
        Write-Step "Khoi dong lai Windows Service $BackendServiceName"
        Start-Service -Name $BackendServiceName -ErrorAction Stop
        (Get-Service -Name $BackendServiceName).WaitForStatus("Running", [TimeSpan]::FromSeconds(30))
    }

    if (-not $SkipHealthCheck) {
        if (-not $BackendServiceName) {
            Write-Warning "Khong co BackendServiceName; health check co the that bai neu API chua chay."
        }
        Write-Step "Kiem tra API health: $HealthUrl"
        $health = Invoke-RestMethod -Uri $HealthUrl -Method Get -TimeoutSec 20
        if ($health.status -ne "ok") { throw "API health khong tra ve status=ok." }
    }

    $restoreSucceeded = $true
    Write-Host ""
    Write-Host "RESTORE HOAN TAT" -ForegroundColor Green
    Write-Host "Database: $DatabaseName ($tableCount tables)"
    Write-Host "Uploads: $($restoredUploadStats.Files) files, $($restoredUploadStats.Bytes) bytes"
    Write-Host "Safety backup: $safetyDirectory"
    Write-Host "Work directory: $workDirectory"
    Write-Host "Bang chinh:"
    $keyCounts | ForEach-Object { Write-Host "  $_" }
}
finally {
    if ($passwordPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
    }
    $databasePassword = $null
    if ($hadPreviousMysqlPassword) {
        $env:MYSQL_PWD = $previousMysqlPassword
    } else {
        Remove-Item Env:MYSQL_PWD -ErrorAction SilentlyContinue
    }
    if (-not $restoreSucceeded -and $BackendServiceName -and $serviceWasRunning) {
        try {
            $failedService = Get-Service -Name $BackendServiceName -ErrorAction SilentlyContinue
            if ($failedService -and $failedService.Status -ne "Stopped") {
                Stop-Service -Name $BackendServiceName -Force -ErrorAction SilentlyContinue
                $failedService = Get-Service -Name $BackendServiceName -ErrorAction SilentlyContinue
                if ($failedService) {
                    $failedService.WaitForStatus("Stopped", [TimeSpan]::FromSeconds(30))
                }
            }
        } catch {
            Write-Warning "Khong the xac nhan service da dung sau loi restore: $($_.Exception.Message)"
        }
        Write-Warning "Restore khong hoan tat; Windows Service da duoc dung de tranh chay voi du lieu dang do."
    }
}
