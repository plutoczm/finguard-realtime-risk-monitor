[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("local", "lan", "public")]
    [string]$Mode = "local",

    [int]$Port = 8090,

    [switch]$NoOpen,

    [switch]$Foreground
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$EnvironmentName = "finguard-risk-monitor"
$EnvironmentFile = Join-Path $Root "environment.yml"
$PublicUrl = "https://finguard-realtime-risk-monitor.vercel.app/"
$ExpectedTitle = "FinGuard"
$ProjectRuntimeDirectory = Join-Path $Root ".runtime"
$ProjectEnvironmentPrefix = Join-Path $ProjectRuntimeDirectory "conda-env"

Set-Location $Root

function Open-DashboardUrl {
    param([string]$Url)

    if (-not $NoOpen) {
        Start-Process -FilePath $Url
    }
}

function Resolve-CondaExecutable {
    $command = Get-Command conda.exe -ErrorAction SilentlyContinue
    $candidates = @(
        $env:CONDA_EXE,
        $(if ($command) { $command.Source }),
        "D:\Anaconda\Miniconda3\Scripts\conda.exe",
        (Join-Path $env:USERPROFILE "miniconda3\Scripts\conda.exe"),
        (Join-Path $env:USERPROFILE "anaconda3\Scripts\conda.exe"),
        (Join-Path $env:ProgramData "miniconda3\Scripts\conda.exe"),
        (Join-Path $env:ProgramData "anaconda3\Scripts\conda.exe")
    ) | Where-Object { $_ } | Select-Object -Unique

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    return $null
}

function Get-CondaEnvironmentPrefix {
    param(
        [string]$CondaExecutable,
        [string]$Name
    )

    $jsonText = (& $CondaExecutable env list --json 2>$null) -join "`n"
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to read the Conda environment list."
    }

    $environmentList = $jsonText | ConvertFrom-Json
    foreach ($prefix in $environmentList.envs) {
        if ((Split-Path $prefix -Leaf) -eq $Name) {
            return $prefix
        }
    }

    return $null
}

function Get-ListeningAddresses {
    param([int]$ListenPort)

    try {
        return @(
            Get-NetTCPConnection -State Listen -LocalPort $ListenPort -ErrorAction Stop |
                Select-Object -ExpandProperty LocalAddress -Unique
        )
    }
    catch {
        return @()
    }
}

function Test-DashboardResponse {
    param([string]$Url)

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3
        return $response.StatusCode -eq 200 -and $response.Content -match $ExpectedTitle
    }
    catch {
        return $false
    }
}

function Get-LanAddresses {
    try {
        return @(
            Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
                Where-Object {
                    $_.IPAddress -ne "127.0.0.1" -and
                    $_.IPAddress -notlike "169.254.*" -and
                    $_.AddressState -eq "Preferred"
                } |
                Select-Object -ExpandProperty IPAddress -Unique
        )
    }
    catch {
        return @()
    }
}

function Write-AccessUrls {
    param([string]$CurrentMode)

    Write-Host ""
    Write-Host "FinGuard is ready" -ForegroundColor Green
    Write-Host "Local URL:  http://127.0.0.1:$Port/"

    if ($CurrentMode -eq "lan") {
        foreach ($address in Get-LanAddresses) {
            Write-Host "LAN URL:    http://${address}:$Port/"
        }
    }

    Write-Host "Public URL: $PublicUrl"
    Write-Host "Use the public URL from devices on a different network."
}

if ($Mode -eq "public") {
    Write-Host "FinGuard public URL: $PublicUrl"
    Open-DashboardUrl -Url $PublicUrl
    exit 0
}

foreach ($directory in @(
    $ProjectRuntimeDirectory,
    (Join-Path $ProjectRuntimeDirectory "temp"),
    (Join-Path $ProjectRuntimeDirectory "cache"),
    (Join-Path $ProjectRuntimeDirectory "conda-pkgs"),
    (Join-Path $ProjectRuntimeDirectory "pip-cache"),
    (Join-Path $ProjectRuntimeDirectory "pycache")
)) {
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
}

$env:TEMP = Join-Path $ProjectRuntimeDirectory "temp"
$env:TMP = $env:TEMP
$env:XDG_CACHE_HOME = Join-Path $ProjectRuntimeDirectory "cache"
$env:PIP_CACHE_DIR = Join-Path $ProjectRuntimeDirectory "pip-cache"
$env:CONDA_PKGS_DIRS = Join-Path $ProjectRuntimeDirectory "conda-pkgs"
$env:PYTHONPYCACHEPREFIX = Join-Path $ProjectRuntimeDirectory "pycache"

$Conda = Resolve-CondaExecutable
if (-not $Conda) {
    throw "Conda was not found. Install Anaconda/Miniconda, or run start.cmd public to use $PublicUrl"
}

$EnvironmentPrefix = if (Test-Path -LiteralPath (Join-Path $ProjectEnvironmentPrefix "python.exe")) {
    $ProjectEnvironmentPrefix
}
else {
    Get-CondaEnvironmentPrefix -CondaExecutable $Conda -Name $EnvironmentName
}

$ProjectDrive = [System.IO.Path]::GetPathRoot($Root)
if ($EnvironmentPrefix -and
    $ProjectDrive -ne "C:\" -and
    [System.IO.Path]::GetPathRoot($EnvironmentPrefix) -eq "C:\") {
    Write-Host "Ignoring the C-drive environment; a project-local environment will be used." -ForegroundColor Yellow
    $EnvironmentPrefix = $null
}

if (-not $EnvironmentPrefix) {
    Write-Host "First run: creating a project-local Conda environment..." -ForegroundColor Cyan
    & $Conda env create --prefix $ProjectEnvironmentPrefix --file $EnvironmentFile --yes
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create the Conda environment."
    }
    $EnvironmentPrefix = $ProjectEnvironmentPrefix
}

if (-not $EnvironmentPrefix) {
    throw "The Conda environment $EnvironmentName could not be located after creation."
}

$Python = Join-Path $EnvironmentPrefix "python.exe"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Python was not found in the environment: $Python"
}

Write-Host "Preparing dashboard demo data..." -ForegroundColor Cyan
& $Python (Join-Path $Root "scripts\generate_vercel_data.py")
if ($LASTEXITCODE -ne 0) {
    throw "Dashboard data generation failed."
}

$LocalUrl = "http://127.0.0.1:$Port/"
$ListeningAddresses = Get-ListeningAddresses -ListenPort $Port
if ($ListeningAddresses.Count -gt 0) {
    if (-not (Test-DashboardResponse -Url $LocalUrl)) {
        throw "Port $Port is used by another application. Choose another port with -Port."
    }

    if ($Mode -eq "lan" -and
        $ListeningAddresses -notcontains "0.0.0.0" -and
        $ListeningAddresses -notcontains "::") {
        throw "The existing service is local-only. Stop the service on port $Port, then run start.cmd lan."
    }

    Write-Host "FinGuard is already running; reusing the existing service." -ForegroundColor Yellow
    Write-AccessUrls -CurrentMode $Mode
    Open-DashboardUrl -Url $LocalUrl
    exit 0
}

$BindAddress = if ($Mode -eq "lan") { "0.0.0.0" } else { "127.0.0.1" }
$ServerScript = Join-Path $Root "dashboard\server.py"

if ($Foreground) {
    Write-AccessUrls -CurrentMode $Mode
    & $Python $ServerScript --host $BindAddress --port $Port
    exit $LASTEXITCODE
}

$RuntimeDirectory = $ProjectRuntimeDirectory
New-Item -ItemType Directory -Force -Path $RuntimeDirectory | Out-Null
$OutputLog = Join-Path $RuntimeDirectory "finguard-dashboard.log"
$ErrorLog = Join-Path $RuntimeDirectory "finguard-dashboard.err.log"
$PidFile = Join-Path $RuntimeDirectory "finguard-dashboard.pid"

$Process = Start-Process `
    -FilePath $Python `
    -ArgumentList @("`"$ServerScript`"", "--host", $BindAddress, "--port", $Port) `
    -WorkingDirectory $Root `
    -RedirectStandardOutput $OutputLog `
    -RedirectStandardError $ErrorLog `
    -WindowStyle Hidden `
    -PassThru

Set-Content -LiteralPath $PidFile -Value $Process.Id -Encoding ASCII

$Ready = $false
for ($attempt = 0; $attempt -lt 40; $attempt += 1) {
    if ($Process.HasExited) {
        break
    }
    if (Test-DashboardResponse -Url $LocalUrl) {
        $Ready = $true
        break
    }
    Start-Sleep -Milliseconds 250
}

if (-not $Ready) {
    $details = if (Test-Path -LiteralPath $ErrorLog) {
        (Get-Content -LiteralPath $ErrorLog -Raw -ErrorAction SilentlyContinue).Trim()
    }
    else {
        ""
    }
    throw "FinGuard failed to start. Error log: $ErrorLog`n$details"
}

Write-AccessUrls -CurrentMode $Mode
Write-Host "Background PID: $($Process.Id)"
Write-Host "Log directory: $RuntimeDirectory"
Open-DashboardUrl -Url $LocalUrl
