# setup_scheduler.ps1
# Registers a daily Windows Task Scheduler job to run the pipeline at 8:00 AM.
# Run once as Administrator: powershell -ExecutionPolicy Bypass -File setup_scheduler.ps1

$TaskName   = "JobHunterDailyCron"
$WorkDir    = Split-Path -Parent $MyInvocation.MyCommand.Definition
$PythonExe  = (Get-Command python -ErrorAction Stop).Source
$ScriptPath = Join-Path $WorkDir "src\run_pipeline.py"

$Action   = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "`"$ScriptPath`"" `
    -WorkingDirectory $WorkDir

$Trigger  = New-ScheduledTaskTrigger -Daily -At "08:00AM"

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable          # catch up if machine was off at 8 AM

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action   $Action `
    -Trigger  $Trigger `
    -Settings $Settings `
    -Force | Out-Null

Write-Host "✓ Scheduled task '$TaskName' created — runs daily at 8:00 AM"
Write-Host "  Script : $ScriptPath"
Write-Host "  Python : $PythonExe"
Write-Host ""
Write-Host "To run manually at any time:"
Write-Host "  python src/run_pipeline.py"
Write-Host ""
Write-Host "To view/edit the task:"
Write-Host "  Task Scheduler → Task Scheduler Library → $TaskName"
