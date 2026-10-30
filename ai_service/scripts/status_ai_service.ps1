# Shows whether the AI service is running and healthy, and where to find its logs.
#   powershell -ExecutionPolicy Bypass -File scripts\status_ai_service.ps1
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root ".env"
$taskName = "SmartLibrary AI Service"

function Get-EnvValue($name, $default) {
    $line = Select-String -Path $envFile -Pattern "^\s*$name\s*=\s*(\S+)" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($line) { $line.Matches[0].Groups[1].Value } else { $default }
}
$hostIp = Get-EnvValue "SERVICE_HOST" "127.0.0.1"
$port = Get-EnvValue "SERVICE_PORT" "8002"

$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
Write-Output ("Autostart task : " + $(if ($task) { $task.State } else { "not installed" }))
$listening = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
Write-Output ("Listening      : " + $(if ($listening) { "$($listening[0].LocalAddress):$port" } else { "NO - nothing on port $port" }))

$url = "http://${hostIp}:$port/api/v1/health"
try {
    $h = (Invoke-RestMethod -Uri $url -TimeoutSec 15).data
    Write-Output "Health         : $($h.status)  (backend_reachable=$($h.backend_reachable), llm_ready=$($h.llm_ready), adapter=$($h.tool_adapter))"
    Write-Output "Share this URL : http://${hostIp}:$port/api/v1"
} catch {
    Write-Output "Health         : NOT RESPONDING at $url"
}
$latest = Get-ChildItem (Join-Path $root "logs") -Filter "ai_service_*.log" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($latest) { Write-Output "Latest log     : $($latest.FullName)" }
