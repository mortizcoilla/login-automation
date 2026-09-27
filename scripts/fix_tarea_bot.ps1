# REQ-094: corrige la tarea del bot de Telegram.
#
# BUG original: la tarea tenia un TimeTrigger con repeticion cada 5 min
# (PT5M) sobre un proceso de larga vida -> cada 5 min el Programador
# intentaba levantar OTRA instancia -> duplicados compitiendo por
# getUpdates (409), el incidente historico de ConflictTerminated.
#
# Diseno correcto para un long-running process:
#   - UN trigger: al iniciar sesion (arranca con el PC, sin repeticion).
#   - MultipleInstances IgnoreNew (nunca dos).
#   - RestartCount 3 x 1 min: si el bot muere, Windows lo revive solo.
#   - ExecutionTimeLimit 3650 dias (sin limite real).

$nombre = 'LoginAutomation-BotRubicita'
$accion = (Get-ScheduledTask -TaskName $nombre).Actions
$principal = (Get-ScheduledTask -TaskName $nombre).Principal

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 3650) `
    -StartWhenAvailable

Set-ScheduledTask -TaskName $nombre -Action $accion -Trigger $trigger -Principal $principal -Settings $settings | Out-Null

$t = Get-ScheduledTask -TaskName $nombre
Write-Output ('Trigger: ' + $t.Triggers[0].CimClass.CimClassName + ' Repetition=[' + $t.Triggers[0].Repetition.Interval + ']')
Write-Output ('MultipleInstances: ' + $t.Settings.MultipleInstancesPolicy)
Write-Output ('Restart: ' + $t.Settings.RestartCount + ' cada ' + $t.Settings.RestartInterval)
