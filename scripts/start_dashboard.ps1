param(
    [int]$Port = 8090
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

python dashboard/server.py --port $Port
