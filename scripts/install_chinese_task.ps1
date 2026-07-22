param(
    [string]$TaskName = "DailyPaperChineseCollection",
    [string]$RunAt = "04:00"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $projectRoot "scripts\run_local_chinese.ps1"
$resolvedRunner = (Resolve-Path -LiteralPath $runner).Path
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument (
    '-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $resolvedRunner
) -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $RunAt
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description (
    "Collect Chinese intelligent-CFD literature daily at local time $RunAt; run when available if missed."
) -Force | Out-Null
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
