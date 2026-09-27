# REQ-096: tarea semanal de papers para Yadira.
# Sabados 09:00 -> python -m src.estudios.oferta_papers
# (analiza notas, busca los 3 papers mas cercanos a su trabajo y le
# manda el listado por Telegram; guarda la oferta para el 1/2/3).

$nombre = 'LoginAutomation-PapersSabado'
$py = 'C:\login-automation\venv\Scripts\pythonw.exe'
$dir = 'C:\login-automation'

$accion = New-ScheduledTaskAction -Execute $py -Argument '-m src.estudios.oferta_papers' -WorkingDirectory $dir
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Saturday -At 09:00
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -StartWhenAvailable

Register-ScheduledTask -TaskName $nombre -Action $accion -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Output ("Registrada: " + $nombre + " (sabados 09:00)")
