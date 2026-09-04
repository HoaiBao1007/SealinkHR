[CmdletBinding()]
param(
    [string]$AppPath = "D:\SEALINK\app",
    [string]$PackageDirectory = "D:\SEALINK\backups\incoming",
    [string]$DatabaseBackupName = "sealink_20260814_102648.sql.gz",
    [string]$UploadsArchiveName = "sealink_transfer_20260814_102648_uploads.zip",
    [string]$ExpectedDatabaseSha256 = "396aefdc79bd88329ce7bc614446ca37ec41db5474691c27887fb70037c7f8cf",
    [string]$ExpectedUploadsSha256 = "4497d82f6b8ad84a493694baf24e49b1684781ed0aa51ad33bcdcbb1cd477c08"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$failures = [System.Collections.Generic.List[string]]::new()

function Write-Check {
    param(
        [string]$Name,
        [bool]$Passed,
        [string]$Detail
    )
    $state = if ($Passed) { "OK" } else { "FAIL" }
    $color = if ($Passed) { "Green" } else { "Red" }
    Write-Host "[$state] $Name - $Detail" -ForegroundColor $color
    if (-not $Passed) { $script:failures.Add("$Name`: $Detail") }
}

function Resolve-Tool {
    param([string[]]$Names)

    foreach ($name in $Names) {
        $command = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($command) { return $command.Source }
    }

    $patterns = @(
        "D:\xampp\mysql\bin\*",
        "C:\Program Files\MariaDB *\bin\*",
        "C:\Program Files\MySQL\MySQL Server *\bin\*",
        "C:\xampp\mysql\bin\*"
    )
    foreach ($pattern in $patterns) {
        foreach ($name in $Names) {
            $match = Get-ChildItem -Path $pattern -File -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -ieq $name } |
                Select-Object -First 1
            if ($match) { return $match.FullName }
        }
    }
    return $null
}

Write-Host "SEALINK SERVER RESTORE PREFLIGHT" -ForegroundColor Cyan
Write-Host "Computer: $env:COMPUTERNAME"
Write-Host "User: $([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)"

$principal = [Security.Principal.WindowsPrincipal]::new(
    [Security.Principal.WindowsIdentity]::GetCurrent()
)
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
Write-Check "Administrator" $isAdmin "PowerShell phai chay bang Run as administrator"

$appFullPath = [System.IO.Path]::GetFullPath($AppPath)
$appDriveRoot = [System.IO.Path]::GetPathRoot($appFullPath)
$appDriveName = $appDriveRoot.TrimEnd("\").TrimEnd(":")
$drive = Get-PSDrive -Name $appDriveName -PSProvider FileSystem -ErrorAction SilentlyContinue
$driveOk = $null -ne $drive -and $drive.Free -ge 1GB
$driveDetail = if ($drive) {
    "Root=$appDriveRoot; Free=$([Math]::Round($drive.Free / 1GB, 2)) GB"
} else { "Khong tim thay o dia cua AppPath: $appDriveRoot" }
Write-Check "Application drive" $driveOk $driveDetail

$packages = @(
    [pscustomobject]@{
        Name = "Database package"
        Path = Join-Path $PackageDirectory $DatabaseBackupName
        Hash = $ExpectedDatabaseSha256.ToLowerInvariant()
    },
    [pscustomobject]@{
        Name = "Uploads package"
        Path = Join-Path $PackageDirectory $UploadsArchiveName
        Hash = $ExpectedUploadsSha256.ToLowerInvariant()
    }
)

foreach ($package in $packages) {
    if (-not (Test-Path -LiteralPath $package.Path -PathType Leaf)) {
        Write-Check $package.Name $false "Missing: $($package.Path)"
        continue
    }
    $item = Get-Item -LiteralPath $package.Path
    $actualHash = (Get-FileHash -LiteralPath $package.Path -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Check $package.Name ($actualHash -eq $package.Hash) "Bytes=$($item.Length); SHA256=$actualHash"
}

$git = Get-Command git.exe -ErrorAction SilentlyContinue
Write-Check "Git" ($null -ne $git) $(if ($git) { $git.Source } else { "git.exe not found" })

$gitDirectory = Join-Path $AppPath ".git"
$repoExists = Test-Path -LiteralPath $gitDirectory -PathType Container
$repoDetail = if ($repoExists -and $git) {
    $commit = (& $git.Source -C $AppPath rev-parse --short HEAD 2>$null | Select-Object -Last 1)
    "Repository=$AppPath; Commit=$commit"
} else {
    "Repository not found: $AppPath"
}
Write-Check "Application repository" $repoExists $repoDetail

$backendPath = Join-Path $AppPath "backend"
Write-Check "Backend directory" (Test-Path -LiteralPath $backendPath -PathType Container) $backendPath

$client = Resolve-Tool -Names @("mariadb.exe", "mysql.exe")
$dump = Resolve-Tool -Names @("mariadb-dump.exe", "mysqldump.exe")
Write-Check "MariaDB client" ($null -ne $client) $(if ($client) { $client } else { "mariadb.exe/mysql.exe not found" })
Write-Check "MariaDB dump" ($null -ne $dump) $(if ($dump) { $dump } else { "mariadb-dump.exe/mysqldump.exe not found" })

$databaseServices = @(Get-Service -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -match "maria|mysql" -or $_.DisplayName -match "MariaDB|MySQL"
})
$runningDatabaseService = @($databaseServices | Where-Object Status -eq "Running")
$serviceDetail = if ($databaseServices.Count) {
    ($databaseServices | ForEach-Object { "$($_.Name)=$($_.Status)" }) -join "; "
} else { "Khong tim thay Windows Service MariaDB/MySQL" }
Write-Check "MariaDB Windows Service" ($runningDatabaseService.Count -gt 0) $serviceDetail

$tcp = Test-NetConnection -ComputerName 127.0.0.1 -Port 3306 -WarningAction SilentlyContinue
Write-Check "MariaDB TCP 3306" $tcp.TcpTestSucceeded "127.0.0.1:3306"

$backendUploads = Join-Path $backendPath "uploads"
$uploadsItem = Get-Item -LiteralPath $backendUploads -Force -ErrorAction SilentlyContinue
if ($uploadsItem) {
    $isReparse = ($uploadsItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
    $detail = if ($isReparse) { "Junction target=$([string]$uploadsItem.Target)" } else { "Physical directory exists" }
    Write-Host "[INFO] Backend uploads - $detail" -ForegroundColor Yellow
} else {
    Write-Host "[INFO] Backend uploads - Not present; restore script will create junction"
}

Write-Host ""
if ($failures.Count) {
    Write-Host "PREFLIGHT FAILED ($($failures.Count) issue(s))" -ForegroundColor Red
    $failures | ForEach-Object { Write-Host " - $_" }
    exit 1
}

Write-Host "PREFLIGHT PASSED" -ForegroundColor Green
Write-Host "MariaDbBinDirectory=$([IO.Path]::GetDirectoryName($client))"
Write-Host "No database or upload data was changed."
