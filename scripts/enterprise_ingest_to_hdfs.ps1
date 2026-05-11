param(
    [string]$RawFile = "enterprise_data\raw\amlworld_transactions_prepared.csv",
    [string]$ProcessedFile = "enterprise_data\processed\finguard_enterprise_transactions.jsonl",
    [string]$RawHdfsPath = "/finguard/enterprise/raw",
    [string]$ProcessedHdfsPath = "/finguard/enterprise/processed"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not $env:HADOOP_HOME) {
    throw "HADOOP_HOME is not set. Current project expects your persistent big-data environment variables."
}

$Hdfs = Join-Path $env:HADOOP_HOME "bin\hdfs.cmd"
if (-not (Test-Path -LiteralPath $Hdfs)) {
    throw "Cannot find hdfs.cmd at $Hdfs"
}

& $Hdfs dfs -mkdir -p $RawHdfsPath
& $Hdfs dfs -mkdir -p $ProcessedHdfsPath

if (Test-Path -LiteralPath $RawFile) {
    & $Hdfs dfs -put -f $RawFile $RawHdfsPath
}

if (Test-Path -LiteralPath $ProcessedFile) {
    & $Hdfs dfs -put -f $ProcessedFile $ProcessedHdfsPath
}

Write-Host "FinGuard enterprise data uploaded to HDFS."
