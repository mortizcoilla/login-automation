# Registrar/operar la tarea de Windows del scheduler del flujo diario.
# REQ-060. Invocado por `python -m src.scheduler.instalar`, no a mano.
#
# Diseno: UNA tarea que dispara cada 30 min, todo el dia, todos los dias.
# El runner (src/scheduler/runner.py) decide con config/calendario.json si
# corresponde correr. Cambiar horarios = editar el JSON, sin tocar aqui.
# La tarea se crea DESACTIVADA (el operador la habilita cuando el PC
# esta listo: venv, credenciales, Chrome).
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("instalar", "activar", "desactivar", "desinstalar", "estado")]
    [string]$Accion
)

$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$taskName = "LoginAutomation-FlujoDiario"

$pythonw = Join-Path $repo "venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    # fallback: python normal (abre consola en cada disparo)
    $pythonw = Join-Path $repo "venv\Scripts\python.exe"
}

switch ($Accion) {

    "instalar" {
        # -Once + repeticion de 30 min sin fin: el patron "latido".
        # StartWhenAvailable: si el PC estaba apagado, corre al encender.
        $action = New-ScheduledTaskAction -Execute $pythonw `
            -Argument "-m src.scheduler.runner --check" `
            -WorkingDirectory $repo
        $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddHours(8) `
            -RepetitionInterval (New-TimeSpan -Minutes 30) `
            -RepetitionDuration (New-TimeSpan -Days 3650)
        $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
            -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -MultipleInstances IgnoreNew `
            -ExecutionTimeLimit (New-TimeSpan -Hours 4)
        # -Force: sobreescribe una tarea previa del mismo nombre.
        Register-ScheduledTask -TaskName $taskName -Action $action `
            -Trigger $trigger -Settings $settings -Force | Out-Null
        # Nace desactivada a proposito.
        Disable-ScheduledTask -TaskName $taskName | Out-Null
        Write-Host "Tarea '$taskName' creada (cada 30 min) y DESACTIVADA."
        Write-Host "Runner: $pythonw -m src.scheduler.runner --check"
        Write-Host "Working dir: $repo"
    }

    "activar" {
        Enable-ScheduledTask -TaskName $taskName | Out-Null
        Write-Host "Tarea '$taskName' ACTIVADA: el calendario manda (config/calendario.json)."
    }

    "desactivar" {
        Disable-ScheduledTask -TaskName $taskName | Out-Null
        Write-Host "Tarea '$taskName' desactivada (configuracion conservada)."
    }

    "desinstalar" {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Tarea '$taskName' eliminada."
    }

    "estado" {
        $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if ($null -eq $task) {
            Write-Host "Tarea '$taskName' no existe. Instalar con: python -m src.scheduler.instalar --instalar"
        } else {
            $info = $task | Get-ScheduledTaskInfo
            Write-Host "Tarea   : $taskName"
            Write-Host "Estado  : $($task.State)"
            Write-Host "Ultima  : $($info.LastRunTime) (resultado: $($info.LastTaskResult))"
            Write-Host "Proxima : $($info.NextRunTime)"
        }
    }
}
