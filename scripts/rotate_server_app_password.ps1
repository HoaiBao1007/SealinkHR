[CmdletBinding()]
param(
    [string]$DatabaseHost = "127.0.0.1",

    [ValidateRange(1, 65535)]
    [int]$DatabasePort = 3306,

    [ValidatePattern("^[A-Za-z0-9_]+$")]
    [string]$DatabaseName = "sealink_hr",

    [ValidatePattern("^[A-Za-z0-9_]+$")]
    [string]$RootUser = "root",

    [ValidatePattern("^[A-Za-z0-9_]+$")]
    [string]$AppUser = "sealink_app",

    [string]$MariaDbBinDirectory = "C:\Program Files\MariaDB 11.4\bin",

    [string]$SecretsFile = "C:\SEALINK\secrets\backend.env",

    [string]$BackendEnvFile = "C:\SEALINK\app\backend\.env"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[SEALINK] $Message" -ForegroundColor Cyan
}

function Convert-SecureStringToPlainText {
    param([Security.SecureString]$Value)
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

function Read-ConfirmedPassword {
    param([string]$Prompt)

    $firstSecure = Read-Host $Prompt -AsSecureString
    $secondSecure = Read-Host "Nhap lai de xac nhan" -AsSecureString
    $first = Convert-SecureStringToPlainText $firstSecure
    $second = Convert-SecureStringToPlainText $secondSecure
    try {
        if ($first.Length -lt 16) { throw "Mat khau phai co it nhat 16 ky tu." }
        if ($first -cne $second) { throw "Hai lan nhap mat khau khong khop." }
        return $first
    } finally {
        $second = $null
    }
}

function Convert-ToSqlStringLiteral {
    param([string]$Value)
    return "'" + $Value.Replace("'", "''") + "'"
}

function Invoke-MariaDbSql {
    param(
        [string]$Executable,
        [string]$User,
        [string]$Password,
        [string]$Sql,
        [string]$Database = ""
    )

    $arguments = @(
        "--host=$DatabaseHost",
        "--port=$DatabasePort",
        "--user=$User",
        "--default-character-set=utf8mb4",
        "--batch",
        "--skip-column-names"
    )
    if ($Database) { $arguments += "--database=$Database" }

    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $Executable
    $startInfo.Arguments = $arguments -join " "
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.EnvironmentVariables["MYSQL_PWD"] = $Password

    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    try {
        if (-not $process.Start()) { throw "Khong khoi dong duoc MariaDB client." }
        $process.StandardInput.WriteLine($Sql)
        $process.StandardInput.Close()
        $output = $process.StandardOutput.ReadToEnd()
        $errorText = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        if ($process.ExitCode -ne 0) {
            throw "MariaDB command that bai (exit code $($process.ExitCode)): $errorText"
        }
        return $output.Trim()
    } finally {
        $process.Dispose()
    }
}

$client = Join-Path $MariaDbBinDirectory "mariadb.exe"
if (-not (Test-Path -LiteralPath $client -PathType Leaf)) {
    $client = Join-Path $MariaDbBinDirectory "mysql.exe"
}
if (-not (Test-Path -LiteralPath $client -PathType Leaf)) {
    throw "Khong tim thay MariaDB client trong $MariaDbBinDirectory"
}
foreach ($path in @($SecretsFile, $BackendEnvFile)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Khong tim thay production env: $path"
    }
}

$envContent = Get-Content -LiteralPath $SecretsFile -Raw
$databaseUrlMatches = [regex]::Matches($envContent, "(?m)^DATABASE_URL=.*$")
if ($databaseUrlMatches.Count -ne 1) {
    throw "Secrets file phai co dung mot dong DATABASE_URL."
}
$backendEnvItem = Get-Item -LiteralPath $BackendEnvFile -Force
if ($backendEnvItem.LinkType -ne "HardLink") {
    throw "Backend .env khong phai hard-link; dung lai de tranh cap nhat sai secrets file."
}

$rootSecure = Read-Host "Nhap mat khau root MariaDB hien tai" -AsSecureString
$rootPassword = Convert-SecureStringToPlainText $rootSecure
$newAppPassword = ""

try {
    Write-Step "Kiem tra root va database $DatabaseName"
    $check = Invoke-MariaDbSql -Executable $client `
        -User $RootUser `
        -Password $rootPassword `
        -Sql "SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='$DatabaseName';"
    if ($check -ne "1") { throw "Khong xac minh duoc database $DatabaseName." }

    $newAppPassword = Read-ConfirmedPassword "Dat mat khau MOI cho $AppUser (toi thieu 16 ky tu)"
    $appLiteral = Convert-ToSqlStringLiteral $newAppPassword
    $rotationSql = @"
SET SESSION sql_mode='NO_BACKSLASH_ESCAPES';
ALTER USER '$AppUser'@'localhost' IDENTIFIED BY $appLiteral;
ALTER USER '$AppUser'@'127.0.0.1' IDENTIFIED BY $appLiteral;
FLUSH PRIVILEGES;
"@

    Write-Step "Xoay mat khau $AppUser trong MariaDB"
    Invoke-MariaDbSql -Executable $client `
        -User $RootUser `
        -Password $rootPassword `
        -Sql $rotationSql | Out-Null

    Write-Step "Kiem tra tai khoan ung dung voi mat khau moi"
    $appCheck = Invoke-MariaDbSql -Executable $client `
        -User $AppUser `
        -Password $newAppPassword `
        -Database $DatabaseName `
        -Sql "SELECT COUNT(*) FROM employees;"
    if ($appCheck -ne "59") {
        throw "Doi soat employees sau khi xoay mat khau khong khop: $appCheck"
    }

    $encodedPassword = [Uri]::EscapeDataString($newAppPassword)
    $newDatabaseUrl = "DATABASE_URL=mysql+pymysql://${AppUser}:${encodedPassword}@${DatabaseHost}:${DatabasePort}/${DatabaseName}?charset=utf8mb4"
    $updatedEnvContent = [regex]::Replace(
        $envContent,
        "(?m)^DATABASE_URL=.*$",
        [Text.RegularExpressions.MatchEvaluator]{ param($match) $newDatabaseUrl }
    )
    [IO.File]::WriteAllText($SecretsFile, $updatedEnvContent, [Text.UTF8Encoding]::new($false))

    Write-Host ""
    Write-Host "APPLICATION DATABASE PASSWORD ROTATION COMPLETE" -ForegroundColor Green
    Write-Host "Database user: $AppUser"
    Write-Host "Verified employees: 59"
    Write-Host "Secrets file and backend hard-link were updated in place."
    Write-Host "The new password was not printed."
} finally {
    $rootPassword = $null
    $newAppPassword = $null
}
