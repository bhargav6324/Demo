# Starts the AI service automatically (hidden, in the background) every time you log in to
# Windows, and starts it right now. No administrator rights needed. Undo: uninstall_autostart.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1
$ErrorActionPreference = "Stop"

$taskName = "SmartLibrary AI Service"
$startScript = Join-Path $PSScriptRoot "start_ai_service.ps1"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$startScript`"" `
    -WorkingDirectory (Split-Path -Parent $PSScriptRoot)
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
# No time limit (the default stops tasks after 3 days); keep running on battery
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
    -Principal $principal -Description "Smart Library AI service (chat/RAG) on port 8002" -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Output "Installed and started '$taskName'. Check it with: powershell -File scripts\status_ai_service.ps1"
