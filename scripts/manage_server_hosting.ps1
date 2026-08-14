[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("start", "stop", "restart", "status")]
    [string]$Action,
    [string]$SiteName = "SEALINK",
    [string]$BackendTaskName = "SEALINK-Backend",
    [ValidateRange(1, 65535)]
    [int]$FrontendPort = 8080,
    [ValidateRange(1, 65535)]
    [int]$BackendPort = 8001
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Import-Module WebAdministration -ErrorAction Stop

switch ($Action) {
    "start" {
        if ((Get-Website -Name $SiteName).State -ne "Started") {
            Start-Website -Name $SiteName
        }
        Start-ScheduledTask -TaskName $BackendTaskName
    }
    "stop" {
        Stop-ScheduledTask -TaskName $BackendTaskName -ErrorAction SilentlyContinue
        Stop-Website -Name $SiteName
    }
    "restart" {
        Stop-ScheduledTask -TaskName $BackendTaskName -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
        if ((Get-Website -Name $SiteName).State -ne "Started") {
            Start-Website -Name $SiteName
        }
        Start-ScheduledTask -TaskName $BackendTaskName
    }
    "status" {
        # No state-changing action.
    }
}

$task = Get-ScheduledTask -TaskName $BackendTaskName
$taskInfo = Get-ScheduledTaskInfo -TaskName $BackendTaskName
$site = Get-Website -Name $SiteName
$healthStatus = "unavailable"
$frontendStatus = "unavailable"
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/health" -TimeoutSec 5
    if ($health.status -eq "ok") { $healthStatus = "ok" }
} catch { }
try {
    $page = Invoke-WebRequest -Uri "http://127.0.0.1:$FrontendPort/" -UseBasicParsing -TimeoutSec 5
    if ($page.StatusCode -eq 200) { $frontendStatus = "ok" }
} catch { }

Write-Host "Backend task state: $($task.State)"
Write-Host "Backend last result: $($taskInfo.LastTaskResult)"
Write-Host "IIS site state: $($site.State)"
Write-Host "Backend health: $healthStatus"
Write-Host "Frontend health: $frontendStatus"
