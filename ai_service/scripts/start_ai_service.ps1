# Runs the AI service and restarts it whenever it stops (crash, Tailscale not up yet, ...).
# Output goes to ai_service\logs\ai_service_<date>.log. Stop it with stop_ai_service.ps1.
#   powershell -ExecutionPolicy Bypass -File scripts\start_ai_service.ps1
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$python = Join-Path $root ".venv\Scripts\python.exe"
$envFile = Join-Path $root ".env"
if (-not (Test-Path $python)) { throw "Missing $python. Create the venv first (see README, Quick start)." }
if (-not (Test-Path $envFile)) { throw "Missing .env. Copy .env.example to .env and fill it in." }

# Read SERVICE_PORT from .env so a second copy doesn't start on a busy port
$portLine = Select-String -Path $envFile -Pattern '^\s*SERVICE_PORT\s*=\s*(\d+)' | Select-Object -First 1
$port = if ($portLine) { [int]$portLine.Matches[0].Groups[1].Value } else { 8002 }
if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
    Write-Output "Port $port is already in use - the AI service is probably already running. Use status_ai_service.ps1."
    exit 0
}

$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$env:PYTHONUNBUFFERED = "1"

while ($true) {
    $log = Join-Path $logDir ("ai_service_{0:yyyy-MM-dd}.log" -f (Get-Date))
    Add-Content -Path $log -Value "[$(Get-Date -Format s)] starting AI service on port $port"
    # cmd handles the redirection so Python's stderr isn't turned into PowerShell errors
    cmd /c "`"$python`" -m app >> `"$log`" 2>&1"
    Add-Content -Path $log -Value "[$(Get-Date -Format s)] AI service stopped (exit code $LASTEXITCODE); restarting in 10 s"
    Start-Sleep -Seconds 10
}
