# Removes the log-in autostart task and stops the running AI service.
#   powershell -ExecutionPolicy Bypass -File scripts\uninstall_autostart.ps1
$taskName = "SmartLibrary AI Service"
& (Join-Path $PSScriptRoot "stop_ai_service.ps1")
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Output "Removed autostart task '$taskName'."
} else {
    Write-Output "No autostart task '$taskName' was installed."
}
