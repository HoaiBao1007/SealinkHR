[CmdletBinding()]
param(
    [string]$AppPath = "C:\SEALINK\app",
    [string]$SecretsFile = "C:\SEALINK\secrets\backend.env",
    [string]$LogDirectory = "C:\SEALINK\logs",
    [string]$SiteName = "SEALINK",
    [string]$AppPoolName = "SEALINK",
    [string]$BackendTaskName = "SEALINK-Backend",
    [ValidateRange(1, 65535)]
    [int]$FrontendPort = 8080,
    [ValidateRange(1, 65535)]
    [int]$BackendPort = 8001,
    [string[]]$AdditionalOrigins = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[SEALINK] $Message" -ForegroundColor Cyan
}

function Get-Origin {
    param(
        [string]$HostName,
        [int]$Port
    )
    if ($Port -eq 80) { return "http://$HostName" }
    return "http://${HostName}:$Port"
}

function Wait-ForHttp {
    param(
        [string]$Uri,
        [switch]$ExpectHealth
    )
    for ($attempt = 1; $attempt -le 45; $attempt++) {
        try {
            if ($ExpectHealth) {
                $response = Invoke-RestMethod -Uri $Uri -Method Get -TimeoutSec 3
                if ($response.status -eq "ok") { return $true }
            } else {
                $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 3
                if ($response.StatusCode -eq 200) { return $true }
            }
        } catch {
            # Wait for the task or IIS worker process to become ready.
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

$principal = [Security.Principal.WindowsPrincipal]::new(
    [Security.Principal.WindowsIdentity]::GetCurrent()
)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Hay chay PowerShell bang Run as administrator."
}
if ($FrontendPort -eq $BackendPort) {
    throw "FrontendPort va BackendPort phai khac nhau."
}

$backendPath = Join-Path $AppPath "backend"
$backendEnv = Join-Path $backendPath ".env"
$python = Join-Path $backendPath ".venv\Scripts\python.exe"
$pythonVenvConfig = Join-Path $backendPath ".venv\pyvenv.cfg"
$frontendDist = Join-Path $AppPath "frontend\dist"
$runnerScript = Join-Path $AppPath "scripts\run_backend_task.ps1"
foreach ($path in @($backendEnv, $SecretsFile, $python, $pythonVenvConfig, (Join-Path $frontendDist "index.html"), $runnerScript)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Thieu hosting runtime file: $path"
    }
}

$backendEnvItem = Get-Item -LiteralPath $backendEnv -Force
if ($backendEnvItem.LinkType -ne "HardLink") {
    throw "Backend .env khong phai hard-link den secrets file."
}

Write-Step "Cap nhat CORS production cho hostname va IP server"
$ipv4Addresses = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {
        $_.IPAddress -ne "127.0.0.1" -and
        $_.IPAddress -notlike "169.254.*" -and
        $_.AddressState -eq "Preferred"
    } |
    Select-Object -ExpandProperty IPAddress -Unique)
$hosts = @("localhost", "127.0.0.1", $env:COMPUTERNAME) + $ipv4Addresses
$origins = @($hosts | ForEach-Object { Get-Origin -HostName $_ -Port $FrontendPort })
foreach ($origin in $AdditionalOrigins) {
    $normalized = $origin.Trim().TrimEnd("/")
    if ($normalized -notmatch "^https?://") {
        throw "Additional origin khong hop le: $origin"
    }
    $origins += $normalized
}
$origins = @($origins | Select-Object -Unique)

$envContent = Get-Content -LiteralPath $SecretsFile -Raw
$corsMatches = [regex]::Matches($envContent, "(?m)^CORS_ORIGINS=.*$")
if ($corsMatches.Count -ne 1) {
    throw "Secrets file phai co dung mot dong CORS_ORIGINS."
}
$corsLine = "CORS_ORIGINS=$($origins -join ',')"
$updatedEnv = [regex]::Replace(
    $envContent,
    "(?m)^CORS_ORIGINS=.*$",
    [Text.RegularExpressions.MatchEvaluator]{ param($match) $corsLine }
)
[IO.File]::WriteAllText($SecretsFile, $updatedEnv, [Text.UTF8Encoding]::new($false))

Write-Step "Bat cac thanh phan IIS static hosting"
$iisFeatures = @(
    "IIS-WebServerRole",
    "IIS-WebServer",
    "IIS-CommonHttpFeatures",
    "IIS-StaticContent",
    "IIS-DefaultDocument",
    "IIS-HttpErrors",
    "IIS-HttpLogging",
    "IIS-RequestFiltering",
    "IIS-ManagementConsole"
)
$missingIisFeatures = @()
foreach ($feature in $iisFeatures) {
    $state = Get-WindowsOptionalFeature -Online -FeatureName $feature -ErrorAction Stop
    if ($state.State -ne "Enabled") {
        $missingIisFeatures += $feature
    }
}
if ($missingIisFeatures.Count -gt 0) {
    $result = Enable-WindowsOptionalFeature `
        -Online `
        -FeatureName $missingIisFeatures `
        -All `
        -NoRestart `
        -ErrorAction Stop
    if ($result.RestartNeeded) {
        throw "Da bat toan bo IIS features con thieu, nhung Windows yeu cau restart. Hay restart Windows va chay lai script."
    }
}

Import-Module WebAdministration -ErrorAction Stop

Write-Step "Cap quyen IIS chi doc frontend dist"
$acl = Get-Acl -LiteralPath $frontendDist
$iisUsersSid = [Security.Principal.SecurityIdentifier]::new("S-1-5-32-568")
$readRule = [Security.AccessControl.FileSystemAccessRule]::new(
    $iisUsersSid,
    [Security.AccessControl.FileSystemRights]::ReadAndExecute,
    [Security.AccessControl.InheritanceFlags]"ContainerInherit, ObjectInherit",
    [Security.AccessControl.PropagationFlags]::None,
    [Security.AccessControl.AccessControlType]::Allow
)
$acl.SetAccessRule($readRule)
Set-Acl -LiteralPath $frontendDist -AclObject $acl

Write-Step "Tao IIS application pool va website"
if (-not (Test-Path "IIS:\AppPools\$AppPoolName")) {
    New-WebAppPool -Name $AppPoolName | Out-Null
}
Set-ItemProperty "IIS:\AppPools\$AppPoolName" -Name managedRuntimeVersion -Value ""
Set-ItemProperty "IIS:\AppPools\$AppPoolName" -Name startMode -Value "AlwaysRunning"

$site = Get-Website -Name $SiteName -ErrorAction SilentlyContinue
if ($site) {
    if ([IO.Path]::GetFullPath([string]$site.PhysicalPath) -ne [IO.Path]::GetFullPath($frontendDist)) {
        throw "IIS site $SiteName da ton tai voi physical path khac: $($site.PhysicalPath)"
    }
    $expectedBinding = "*:${FrontendPort}:"
    $hasBinding = @(Get-WebBinding -Name $SiteName -Protocol http | Where-Object bindingInformation -eq $expectedBinding).Count -gt 0
    if (-not $hasBinding) {
        throw "IIS site $SiteName da ton tai nhung khong co binding $expectedBinding"
    }
} else {
    $frontendListener = Get-NetTCPConnection -State Listen -LocalPort $FrontendPort -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($frontendListener) {
        throw "Port frontend $FrontendPort dang duoc PID $($frontendListener.OwningProcess) su dung, nhung IIS site $SiteName chua ton tai."
    }
    New-Website `
        -Name $SiteName `
        -Port $FrontendPort `
        -IPAddress "*" `
        -PhysicalPath $frontendDist `
        -ApplicationPool $AppPoolName | Out-Null
}
if ((Get-WebAppPoolState -Name $AppPoolName).Value -ne "Started") {
    Start-WebAppPool -Name $AppPoolName
}
if ((Get-Website -Name $SiteName).State -ne "Started") {
    Start-Website -Name $SiteName
}

Write-Step "Dang ky backend Windows Scheduled Task"
if (Get-ScheduledTask -TaskName $BackendTaskName -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $BackendTaskName -ErrorAction SilentlyContinue
    for ($attempt = 1; $attempt -le 15; $attempt++) {
        if (-not (Get-NetTCPConnection -State Listen -LocalPort $BackendPort -ErrorAction SilentlyContinue)) {
            break
        }
        Start-Sleep -Seconds 1
    }
}
$backendListener = Get-NetTCPConnection -State Listen -LocalPort $BackendPort -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($backendListener) {
    throw "Port backend $BackendPort dang duoc PID $($backendListener.OwningProcess) su dung. Hay dung tien trinh backend khac truoc."
}
$taskArguments = "-NoProfile -ExecutionPolicy Bypass -File `"$runnerScript`" -AppPath `"$AppPath`" -LogDirectory `"$LogDirectory`" -BackendPort $BackendPort"
$windowsPowerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
if (-not (Test-Path -LiteralPath $windowsPowerShell -PathType Leaf)) {
    throw "Khong tim thay Windows PowerShell: $windowsPowerShell"
}
$action = New-ScheduledTaskAction `
    -Execute $windowsPowerShell `
    -Argument $taskArguments `
    -WorkingDirectory $backendPath
$trigger = New-ScheduledTaskTrigger -AtStartup
$venvConfigContent = Get-Content -LiteralPath $pythonVenvConfig -Raw
$usesMicrosoftStorePython = $venvConfigContent -match "(?i)\\WindowsApps\\"
if ($usesMicrosoftStorePython) {
    $taskUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    Write-Step "Python Microsoft Store: backend task chay bang $taskUser (S4U, khong luu mat khau)"
    $taskPrincipal = New-ScheduledTaskPrincipal `
        -UserId $taskUser `
        -LogonType S4U `
        -RunLevel Highest
} else {
    $taskUser = "SYSTEM"
    $taskPrincipal = New-ScheduledTaskPrincipal `
        -UserId $taskUser `
        -LogonType ServiceAccount `
        -RunLevel Highest
}
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 10 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew
Register-ScheduledTask `
    -TaskName $BackendTaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $taskPrincipal `
    -Settings $settings `
    -Description "SEALINK FastAPI backend ($taskUser); managed by C:\SEALINK\app\scripts" `
    -Force | Out-Null

Write-Step "Tao firewall rules cho mang noi bo"
$firewallRules = @(
    [pscustomobject]@{ Name = "SEALINK-Backend-$BackendPort"; Port = $BackendPort },
    [pscustomobject]@{ Name = "SEALINK-Frontend-$FrontendPort"; Port = $FrontendPort }
)
foreach ($rule in $firewallRules) {
    if (-not (Get-NetFirewallRule -Name $rule.Name -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule `
            -Name $rule.Name `
            -DisplayName $rule.Name `
            -Direction Inbound `
            -Action Allow `
            -Protocol TCP `
            -LocalPort $rule.Port `
            -RemoteAddress LocalSubnet `
            -Profile Any | Out-Null
    }
}

Start-ScheduledTask -TaskName $BackendTaskName

Write-Step "Kiem tra backend va IIS frontend"
$healthUrl = "http://127.0.0.1:$BackendPort/health"
$frontendUrl = "http://127.0.0.1:$FrontendPort/"
if (-not (Wait-ForHttp -Uri $healthUrl -ExpectHealth)) {
    $taskInfo = Get-ScheduledTaskInfo -TaskName $BackendTaskName
    $stderrLog = Join-Path $LogDirectory "backend-service.stderr.log"
    $bootstrapLog = Join-Path $LogDirectory "backend-service.bootstrap.log"
    $logParts = @()
    foreach ($logPath in @($bootstrapLog, $stderrLog)) {
        if (Test-Path -LiteralPath $logPath) {
            $logParts += "--- $logPath ---"
            $logParts += (Get-Content -LiteralPath $logPath -Tail 80 -ErrorAction SilentlyContinue | Out-String)
        }
    }
    throw "Backend khong san sang. LastTaskResult=$($taskInfo.LastTaskResult).`n$($logParts -join [Environment]::NewLine)"
}
if (-not (Wait-ForHttp -Uri $frontendUrl)) {
    throw "IIS frontend khong san sang: $frontendUrl"
}

Write-Host ""
Write-Host "SEALINK WINDOWS HOSTING IS RUNNING" -ForegroundColor Green
Write-Host "Backend task: $BackendTaskName"
Write-Host "Health: $healthUrl -> ok"
Write-Host "Frontend URLs:"
$hosts | Select-Object -Unique | ForEach-Object {
    Write-Host "  $(Get-Origin -HostName $_ -Port $FrontendPort)"
}
Write-Host "Firewall access is limited to LocalSubnet."
Write-Host "Logs: $LogDirectory"
