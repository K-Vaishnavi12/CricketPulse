# CricketPulse - one-command startup for Windows
# Usage: .\scripts\start_all.ps1

param(
    [switch]$SkipDocker,
    [switch]$SkipBootstrap
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "   CricketPulse - Live Match Intelligence     " -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""

# --- 1. Docker ---
if (-not $SkipDocker) {
    Write-Host "[1/4] Starting Kafka + Airflow via Docker Compose..." -ForegroundColor Yellow
    docker compose -f docker/docker-compose.yml up -d
    Write-Host "      Waiting 45s for Kafka to be ready..." -ForegroundColor DarkGray
    Start-Sleep -Seconds 45
} else {
    Write-Host "[1/4] Skipping Docker (--SkipDocker)" -ForegroundColor DarkGray
}

# --- 2. Bootstrap (schema + ML training) ---
if (-not $SkipBootstrap) {
    Write-Host "[2/4] Bootstrapping warehouse + training ML models..." -ForegroundColor Yellow
    python scripts/bootstrap.py
} else {
    Write-Host "[2/4] Skipping bootstrap (--SkipBootstrap)" -ForegroundColor DarkGray
}

# --- 3. Launch producer + consumer in new windows ---
Write-Host "[3/4] Launching producer + consumer in new PowerShell windows..." -ForegroundColor Yellow
$here = (Get-Location).Path
Start-Process powershell -ArgumentList "-NoExit","-Command","cd '$here'; python -m src.consumer.ball_consumer"
Start-Sleep -Seconds 4
Start-Process powershell -ArgumentList "-NoExit","-Command","cd '$here'; python -m src.producer.match_producer"

# --- 4. Launch dashboard in current window ---
Write-Host "[4/4] Starting Streamlit dashboard on http://localhost:8501" -ForegroundColor Green
Write-Host ""
Write-Host "  Kafka UI  -> http://localhost:8090" -ForegroundColor Cyan
Write-Host "  Airflow   -> http://localhost:8080  (admin / admin)" -ForegroundColor Cyan
Write-Host "  Dashboard -> http://localhost:8501" -ForegroundColor Cyan
Write-Host ""
streamlit run src/dashboard/app.py
