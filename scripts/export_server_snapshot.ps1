[CmdletBinding()]
param(
    [string]$Repository = "C:\SEALINK\app",
    [string]$OutputDirectory = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Invoke-GitLines {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $output = @(& git -C $Repository @Arguments)
    if ($LASTEXITCODE -ne 0) {
        throw "Git command failed: git -C $Repository $($Arguments -join ' ')"
    }
    return @($output | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
}

if (-not (Test-Path -LiteralPath (Join-Path $Repository ".git"))) {
    throw "Git repository not found: $Repository"
}

if (-not $OutputDirectory) {
    $share = Get-SmbShare -Name "SEALINK-TRANSFER" -ErrorAction Stop
    $OutputDirectory = $share.Path
}

if (-not (Test-Path -LiteralPath $OutputDirectory -PathType Container)) {
    throw "Output directory not found: $OutputDirectory"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$snapshotName = "server_snapshot_$stamp"
$snapshotDirectory = Join-Path $OutputDirectory $snapshotName
$archivePath = "$snapshotDirectory.zip"

New-Item -ItemType Directory -Path $snapshotDirectory -Force | Out-Null

$baseCommitLines = @(Invoke-GitLines -Arguments @("rev-parse", "HEAD"))
$branchLines = @(Invoke-GitLines -Arguments @("branch", "--show-current"))
$baseCommit = $baseCommitLines[0]
$branch = if ($branchLines.Count -gt 0) { $branchLines[0] } else { "DETACHED" }
$status = @(Invoke-GitLines -Arguments @("status", "--porcelain=v1", "-uall"))
$trackedFiles = @(Invoke-GitLines -Arguments @("diff", "--name-only", "--diff-filter=ACMRTUXB", "HEAD"))
$untrackedFiles = @(Invoke-GitLines -Arguments @("ls-files", "--others", "--exclude-standard"))
$files = @($trackedFiles + $untrackedFiles | Sort-Object -Unique)

foreach ($relativePath in $files) {
    $windowsRelativePath = $relativePath.Replace("/", "\")
    $sourcePath = Join-Path $Repository $windowsRelativePath
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
        throw "Snapshot source file not found: $sourcePath"
    }

    $destinationPath = Join-Path $snapshotDirectory $windowsRelativePath
    $destinationParent = Split-Path -Parent $destinationPath
    New-Item -ItemType Directory -Path $destinationParent -Force | Out-Null
    Copy-Item -LiteralPath $sourcePath -Destination $destinationPath -Force
}

$utf8 = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText((Join-Path $snapshotDirectory "_base_commit.txt"), "$baseCommit`n", $utf8)
[IO.File]::WriteAllText((Join-Path $snapshotDirectory "_branch.txt"), "$branch`n", $utf8)
[IO.File]::WriteAllLines((Join-Path $snapshotDirectory "_status.txt"), [string[]]$status, $utf8)
[IO.File]::WriteAllLines((Join-Path $snapshotDirectory "_files.txt"), [string[]]$files, $utf8)

Compress-Archive -Path (Join-Path $snapshotDirectory "*") -DestinationPath $archivePath -CompressionLevel Optimal -Force

$archive = Get-Item -LiteralPath $archivePath
$hash = Get-FileHash -LiteralPath $archivePath -Algorithm SHA256

Write-Host "SERVER SNAPSHOT EXPORTED" -ForegroundColor Green
Write-Host "Repository : $Repository"
Write-Host "Base commit: $baseCommit"
Write-Host "Branch     : $branch"
Write-Host "Files      : $($files.Count)"
Write-Host "Archive    : $($archive.FullName)"
Write-Host "Bytes      : $($archive.Length)"
Write-Host "SHA256     : $($hash.Hash)"
