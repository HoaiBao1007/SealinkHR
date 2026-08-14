[CmdletBinding()]
param(
    [string]$SharePath = "\\DESKTOP-RTG2F0H\SEALINK-TRANSFER",

    [string]$DatabaseBackup = "D:\SEALINK WEB\backups\sealink_20260814_102648.sql.gz",

    [string]$UploadsBackup = "D:\SEALINK WEB\backups\sealink_transfer_20260814_102648_uploads.zip",

    [string]$ExpectedDatabaseSha256 = "396aefdc79bd88329ce7bc614446ca37ec41db5474691c27887fb70037c7f8cf",

    [string]$ExpectedUploadsSha256 = "4497d82f6b8ad84a493694baf24e49b1684781ed0aa51ad33bcdcbb1cd477c08",

    [PSCredential]$Credential
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

function Test-ShareAccess {
    param([string]$Path)
    try {
        Get-ChildItem -LiteralPath $Path -Force -ErrorAction Stop | Select-Object -First 1 | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Copy-VerifiedFile {
    param(
        [string]$Source,
        [string]$DestinationDirectory,
        [string]$ExpectedHash
    )

    $fileName = [System.IO.Path]::GetFileName($Source)
    $destination = Join-Path $DestinationDirectory $fileName
    $partial = Join-Path $DestinationDirectory "$fileName.partial.$PID"

    if (Test-Path -LiteralPath $destination -PathType Leaf) {
        $existingHash = Get-Sha256 $destination
        if ($existingHash -eq $ExpectedHash) {
            Write-Step "$fileName da ton tai va checksum dung; bo qua copy."
            return [pscustomobject]@{
                Path = $destination
                Bytes = (Get-Item -LiteralPath $destination).Length
                Sha256 = $existingHash
            }
        }

        $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $conflictName = "$fileName.conflict.$timestamp"
        Write-Warning "$fileName da ton tai nhung checksum sai; doi ten thanh $conflictName."
        Move-Item -LiteralPath $destination -Destination (Join-Path $DestinationDirectory $conflictName)
    }

    try {
        Write-Step "Copy $fileName qua file tam"
        Copy-Item -LiteralPath $Source -Destination $partial -Force
        $partialHash = Get-Sha256 $partial
        if ($partialHash -ne $ExpectedHash) {
            throw "Checksum file tam khong khop: $fileName"
        }
        Move-Item -LiteralPath $partial -Destination $destination
    } finally {
        if (Test-Path -LiteralPath $partial -PathType Leaf) {
            Remove-Item -LiteralPath $partial -Force
        }
    }

    $destinationHash = Get-Sha256 $destination
    if ($destinationHash -ne $ExpectedHash) {
        throw "Checksum file dich khong khop sau copy: $fileName"
    }

    return [pscustomobject]@{
        Path = $destination
        Bytes = (Get-Item -LiteralPath $destination).Length
        Sha256 = $destinationHash
    }
}

if (-not $SharePath.StartsWith("\\")) {
    throw "SharePath phai la duong dan UNC, vi du \\SERVER\SHARE."
}

$sources = @(
    [pscustomobject]@{ Path = $DatabaseBackup; Hash = $ExpectedDatabaseSha256.ToLowerInvariant() },
    [pscustomobject]@{ Path = $UploadsBackup; Hash = $ExpectedUploadsSha256.ToLowerInvariant() }
)

Write-Step "Kiem tra file va checksum nguon"
foreach ($source in $sources) {
    if (-not (Test-Path -LiteralPath $source.Path -PathType Leaf)) {
        throw "Khong tim thay file nguon: $($source.Path)"
    }
    $sourceHash = Get-Sha256 $source.Path
    if ($sourceHash -ne $source.Hash) {
        throw "Checksum nguon khong khop: $($source.Path). Expected=$($source.Hash) Actual=$sourceHash"
    }
}

if (-not (Test-ShareAccess $SharePath)) {
    if (-not $Credential) {
        $Credential = Get-Credential -Message "Nhap tai khoan co quyen ghi vao $SharePath"
    }
    if (-not $Credential) {
        throw "Da huy do chua co credential SMB."
    }

    Write-Step "Ket noi SMB bang credential duoc nhap an toan"
    New-SmbMapping -RemotePath $SharePath -Credential $Credential -Persistent $true -SaveCredentials | Out-Null
}

if (-not (Test-ShareAccess $SharePath)) {
    throw "Khong truy cap duoc SMB share sau khi xac thuc: $SharePath"
}

Write-Step "Copy va xac minh hai goi backup"
$results = foreach ($source in $sources) {
    Copy-VerifiedFile -Source $source.Path -DestinationDirectory $SharePath -ExpectedHash $source.Hash
}

Write-Host ""
Write-Host "TRANSFER HOAN TAT" -ForegroundColor Green
$results | Format-Table Path, Bytes, Sha256 -AutoSize
Write-Host "Chi moi copy backup; chua co thao tac restore nao duoc chay."
