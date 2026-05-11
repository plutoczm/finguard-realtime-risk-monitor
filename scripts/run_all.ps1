param(
    [ValidateSet("up", "down", "topics", "generate", "produce", "package", "submit-job", "logs", "clean", "test", "all")]
    [string]$Action = "all",
    [int]$Qps = 50,
    [int]$Duration = 120,
    [double]$AbnormalRate = 0.15
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Wait-Port {
    param(
        [string]$HostName,
        [int]$Port,
        [int]$TimeoutSec = 120
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $client = [Net.Sockets.TcpClient]::new()
            $client.Connect($HostName, $Port)
            $client.Close()
            return
        }
        catch {
            Start-Sleep -Seconds 2
        }
    }

    throw "Port $HostName`:$Port is not ready after $TimeoutSec seconds."
}

function Create-Topics {
    docker compose exec kafka bash /scripts/create_topics.sh
}

function Package-Job {
    Push-Location "flink-job"
    try {
        mvn -q -DskipTests package
    }
    finally {
        Pop-Location
    }
}

function Submit-Job {
    Package-Job
    docker compose exec flink-jobmanager flink run -d `
        -c com.finguard.RiskMonitorJob `
        /opt/flink/usrlib/finguard-risk-monitor-1.0.0.jar `
        --bootstrap-servers kafka:29092 `
        --transaction-topic payment_transaction_events `
        --metric-output file:///opt/finguard/data/output/realtime_metrics `
        --alert-output file:///opt/finguard/data/alerts/risk_alerts `
        --late-output file:///opt/finguard/data/late_events `
        --dead-letter-output file:///opt/finguard/data/output/dead_letter
}

switch ($Action) {
    "up" {
        docker compose up -d
        Wait-Port -HostName "localhost" -Port 9092
        Wait-Port -HostName "localhost" -Port 8081
        Write-Host "FinGuard stack is up. Kafka localhost:9092, Flink UI http://localhost:8081"
    }
    "down" {
        docker compose down
    }
    "topics" {
        Create-Topics
    }
    "generate" {
        python producer/generate_transactions.py --count 1000 --output data/sample_events/transactions.json --mode mixed --abnormal-rate $AbnormalRate
    }
    "produce" {
        python producer/kafka_producer.py --bootstrap-server localhost:9092 --topic payment_transaction_events --mode mixed --abnormal-rate $AbnormalRate --qps $Qps --duration $Duration
    }
    "package" {
        Package-Job
    }
    "submit-job" {
        Submit-Job
    }
    "logs" {
        docker compose logs -f --tail=200
    }
    "clean" {
        bash scripts/clean.sh
    }
    "test" {
        python -m pytest -q
        Push-Location "flink-job"
        try {
            mvn -q test
        }
        finally {
            Pop-Location
        }
    }
    "all" {
        docker compose up -d
        Wait-Port -HostName "localhost" -Port 9092
        Wait-Port -HostName "localhost" -Port 8081
        Create-Topics
        python producer/generate_transactions.py --count 1000 --output data/sample_events/transactions.json --mode mixed --abnormal-rate $AbnormalRate
        Submit-Job
        Write-Host "FinGuard is running. Start producer in another terminal if needed:"
        Write-Host "python producer/kafka_producer.py --bootstrap-server localhost:9092 --topic payment_transaction_events --qps $Qps --duration $Duration --mode mixed --abnormal-rate $AbnormalRate"
    }
}
