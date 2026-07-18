[CmdletBinding()]
param(
    [int]$Port = 8090
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$RuntimeDirectory = Join-Path $Root ".runtime"
$PidFile = Join-Path $RuntimeDirectory "finguard-dashboard.pid"
$ExpectedScript = Join-Path $Root "dashboard\server.py"

function Get-ProjectProcess {
    param([int]$ProcessId)

    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
    if (-not $process) {
        return $null
    }

    $commandLine = [string]$process.CommandLine
    if ($commandLine -notmatch [regex]::Escape($ExpectedScript)) {
        return $null
    }

    return $process
}

$CandidateIds = @()
if (Test-Path -LiteralPath $PidFile -PathType Leaf) {
    $savedPid = 0
    if ([int]::TryParse((Get-Content -LiteralPath $PidFile -Raw).Trim(), [ref]$savedPid)) {
        $CandidateIds += $savedPid
    }
}

try {
    $CandidateIds += @(
        Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop |
            Select-Object -ExpandProperty OwningProcess -Unique
    )
}
catch {
}

$ProjectProcesses = @(
    $CandidateIds |
        Select-Object -Unique |
        ForEach-Object { Get-ProjectProcess -ProcessId $_ } |
        Where-Object { $_ }
)

if (-not $ProjectProcesses.Count) {
    if (Test-Path -LiteralPath $PidFile) {
        Remove-Item -LiteralPath $PidFile -Force
    }
    Write-Host "FinGuard is not running."
    exit 0
}

foreach ($process in $ProjectProcesses) {
    Stop-Process -Id $process.ProcessId -ErrorAction Stop
}

foreach ($process in $ProjectProcesses) {
    try {
        Wait-Process -Id $process.ProcessId -Timeout 5 -ErrorAction Stop
    }
    catch {
        if (Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue) {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
        }
    }
}

if (Test-Path -LiteralPath $PidFile) {
    Remove-Item -LiteralPath $PidFile -Force
}

Write-Host "FinGuard stopped."
