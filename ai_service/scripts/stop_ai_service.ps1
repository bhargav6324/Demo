# Stops the AI service: the restart loop first (so it doesn't come back), then the server.
#   powershell -ExecutionPolicy Bypass -File scripts\stop_ai_service.ps1
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root ".env"
$taskName = "SmartLibrary AI Service"

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
}
# Any restart loop started from this folder (scheduled task or manual)
Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" |
    Where-Object { $_.CommandLine -like "*start_ai_service.ps1*" -and $_.ProcessId -ne $PID } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

# The server: whatever owns SERVICE_PORT. (A venv's python.exe is only a launcher on
# Windows; the real server is its child, so match on the listening port instead.)
$portLine = Select-String -Path $envFile -Pattern '^\s*SERVICE_PORT\s*=\s*(\d+)' -ErrorAction SilentlyContinue | Select-Object -First 1
$port = if ($portLine) { [int]$portLine.Matches[0].Groups[1].Value } else { 8002 }
$owners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique
foreach ($procId in $owners) {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $procId"
    $parent = if ($proc.ParentProcessId) { Get-CimInstance Win32_Process -Filter "ProcessId = $($proc.ParentProcessId)" }
    # Only the venv launcher (python.exe), never a terminal the user started it from
    if ($parent -and $parent.Name -eq "python.exe") { Stop-Process -Id $parent.ProcessId -Force -ErrorAction SilentlyContinue }
    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
}
Write-Output ("Stopped AI service" + $(if ($owners) { " (port $port freed)." } else { " (nothing was listening on port $port)." }))
