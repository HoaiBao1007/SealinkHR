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

    [string]$BackendEnvFile = "C:\SEALINK\app\backend\.env",

    [string]$CorsOrigins = "http://localhost"
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
    param(
        [string]$Prompt,
        [int]$MinimumLength = 16
    )

    $firstSecure = Read-Host $Prompt -AsSecureString
    $secondSecure = Read-Host "Nhap lai de xac nhan" -AsSecureString
    $first = Convert-SecureStringToPlainText $firstSecure
    $second = Convert-SecureStringToPlainText $secondSecure
    try {
        if ($first.Length -lt $MinimumLength) {
            throw "Mat khau phai co it nhat $MinimumLength ky tu."
        }
        if ($first -cne $second) {
            throw "Hai lan nhap mat khau khong khop."
        }
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

function New-RandomSecret {
    param([int]$Bytes = 48)
    $buffer = New-Object byte[] $Bytes
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($buffer) }
    finally { $generator.Dispose() }
    return [Convert]::ToBase64String($buffer).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

function Set-PrivateFileAcl {
    param([string]$Path)

    $acl = [Security.AccessControl.FileSecurity]::new()
    $acl.SetAccessRuleProtection($true, $false)
    $rights = [Security.AccessControl.FileSystemRights]::FullControl
    $allow = [Security.AccessControl.AccessControlType]::Allow
    foreach ($sidValue in @("S-1-5-18", "S-1-5-32-544")) {
        $sid = [Security.Principal.SecurityIdentifier]::new($sidValue)
        $rule = [Security.AccessControl.FileSystemAccessRule]::new($sid, $rights, $allow)
        $acl.AddAccessRule($rule)
    }
    $currentSid = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $currentRule = [Security.AccessControl.FileSystemAccessRule]::new($currentSid, $rights, $allow)
    $acl.AddAccessRule($currentRule)
    Set-Acl -LiteralPath $Path -AclObject $acl
}

$client = Join-Path $MariaDbBinDirectory "mariadb.exe"
if (-not (Test-Path -LiteralPath $client -PathType Leaf)) {
    $client = Join-Path $MariaDbBinDirectory "mysql.exe"
}
if (-not (Test-Path -LiteralPath $client -PathType Leaf)) {
    throw "Khong tim thay MariaDB client trong $MariaDbBinDirectory"
}
if (-not (Test-Path -LiteralPath (Split-Path $SecretsFile -Parent) -PathType Container)) {
    throw "Secrets directory chua ton tai: $(Split-Path $SecretsFile -Parent)"
}
if (-not (Test-Path -LiteralPath (Split-Path $BackendEnvFile -Parent) -PathType Container)) {
    throw "Backend directory chua ton tai: $(Split-Path $BackendEnvFile -Parent)"
}
if (Test-Path -LiteralPath $SecretsFile -PathType Leaf) {
    throw "Secrets file da ton tai; khong ghi de: $SecretsFile"
}
if (Test-Path -LiteralPath $BackendEnvFile -PathType Leaf) {
    throw "Backend .env da ton tai; khong ghi de: $BackendEnvFile"
}

$currentRootSecure = Read-Host "Nhap mat khau root MariaDB hien tai (Enter neu dang trong)" -AsSecureString
$currentRootPassword = Convert-SecureStringToPlainText $currentRootSecure
$newRootPassword = ""
$appPassword = ""

try {
    Write-Step "Kiem tra quyen root va database $DatabaseName"
    $accountAndDatabaseCheck = Invoke-MariaDbSql -Executable $client `
        -User $RootUser `
        -Password $currentRootPassword `
        -Sql "SELECT CONCAT(CURRENT_USER(), '|', COUNT(*)) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='$DatabaseName';"
    if ($accountAndDatabaseCheck -notmatch "^([^@|]+)@([^|]+)\|1$") {
        throw "Khong xac minh duoc root account/database: $accountAndDatabaseCheck"
    }
    $authenticatedRootUser = $Matches[1]
    $authenticatedRootHost = $Matches[2]
    if ($authenticatedRootUser -cne $RootUser) {
        throw "Ket noi khong dung root account mong doi: $accountAndDatabaseCheck"
    }

    $newRootPassword = Read-ConfirmedPassword "Dat mat khau root moi (toi thieu 16 ky tu)"
    $appPassword = Read-ConfirmedPassword "Dat mat khau cho $AppUser (toi thieu 16 ky tu)"

    $rootLiteral = Convert-ToSqlStringLiteral $newRootPassword
    $appLiteral = Convert-ToSqlStringLiteral $appPassword
    $rootHostLiteral = Convert-ToSqlStringLiteral $authenticatedRootHost
    $securitySql = @"
SET SESSION sql_mode='NO_BACKSLASH_ESCAPES';
ALTER USER '$RootUser'@$rootHostLiteral IDENTIFIED BY $rootLiteral;
CREATE USER IF NOT EXISTS '$AppUser'@'localhost' IDENTIFIED BY $appLiteral;
ALTER USER '$AppUser'@'localhost' IDENTIFIED BY $appLiteral;
CREATE USER IF NOT EXISTS '$AppUser'@'127.0.0.1' IDENTIFIED BY $appLiteral;
ALTER USER '$AppUser'@'127.0.0.1' IDENTIFIED BY $appLiteral;
GRANT ALL PRIVILEGES ON ``$DatabaseName``.* TO '$AppUser'@'localhost';
GRANT ALL PRIVILEGES ON ``$DatabaseName``.* TO '$AppUser'@'127.0.0.1';
FLUSH PRIVILEGES;
"@

    Write-Step "Bao mat root va tao tai khoan $AppUser gioi han trong $DatabaseName"
    Invoke-MariaDbSql -Executable $client `
        -User $RootUser `
        -Password $currentRootPassword `
        -Sql $securitySql | Out-Null

    Write-Step "Kiem tra tai khoan ung dung"
    $appCheck = Invoke-MariaDbSql -Executable $client `
        -User $AppUser `
        -Password $appPassword `
        -Database $DatabaseName `
        -Sql "SELECT CONCAT(DATABASE(), '|', COUNT(*)) FROM employees;"
    if ($appCheck -ne "$DatabaseName|59") {
        throw "Tai khoan ung dung ket noi duoc nhung doi soat employees khong khop: $appCheck"
    }

    $encodedPassword = [Uri]::EscapeDataString($appPassword)
    $secretKey = New-RandomSecret
    $envContent = @"
APP_NAME=SEALINK Attendance API
APP_ENV=production
APP_HOST=127.0.0.1
APP_PORT=8001
SECRET_KEY=$secretKey
TOKEN_EXPIRE_SECONDS=3600
DATABASE_URL=mysql+pymysql://${AppUser}:${encodedPassword}@${DatabaseHost}:${DatabasePort}/${DatabaseName}?charset=utf8mb4
CORS_ORIGINS=$CorsOrigins
CORS_ORIGIN_REGEX=
TRUSTED_DEVICE_COOKIE_SECURE=false
TRUSTED_DEVICE_ALLOW_SAME_IP_RECOVERY=true
"@

    Write-Step "Tao production secrets ngoai repository"
    [IO.File]::WriteAllText($SecretsFile, $envContent, [Text.UTF8Encoding]::new($false))
    Set-PrivateFileAcl $SecretsFile
    New-Item -ItemType HardLink -Path $BackendEnvFile -Target $SecretsFile | Out-Null

    Write-Host ""
    Write-Host "DATABASE SECURITY CONFIGURATION COMPLETE" -ForegroundColor Green
    Write-Host "Database user: $AppUser"
    Write-Host "Secrets: $SecretsFile"
    Write-Host "Backend env hardlink: $BackendEnvFile"
    Write-Host "Verified employees: 59"
    Write-Host "Passwords and SECRET_KEY were not printed."
} finally {
    $currentRootPassword = $null
    $newRootPassword = $null
    $appPassword = $null
}
