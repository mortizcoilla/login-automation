# Registrar/operar la tarea de Windows del bot Rubicita (paso 2a).
# Invocado por el operador o documentado en INSTALACION. Requiere que
# el repo este instalado en C:\login-automation-bot (worktree de la
# rama feat/telegram-bot-rubicita) con su venv.
#
# La tarea arranca el bot al iniciar sesion (pythonw, sin ventana) y
# se puede arrancar/detener a mano sin cerrar sesion.
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("instalar", "activar", "desactivar", "detener", "desinstalar", "estado", "arrancar")]
    [string]$Accion
)

$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$taskName = "LoginAutomation-BotRubicita"

$pythonw = Join-Path $repo "venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    $pythonw = Join-Path $repo "venv\Scripts\python.exe"
}

switch ($Accion) {

    "instalar" {
        # Patron "latido" (mismo del cron REQ-060): dispara cada 5 min;
        # MultipleInstances IgnoreNew ignora el disparo si ya corre, y
        # StartWhenAvailable lo reviva tras un reinicio del PC. Sin
        # trigger AtLogOn a proposito: ese requiere permisos de admin.
        $action = New-ScheduledTaskAction -Execute $pythonw `
            -Argument "-m src.telegram_bot.app" `
            -WorkingDirectory $repo
        $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
            -RepetitionInterval (New-TimeSpan -Minutes 5) `
            -RepetitionDuration (New-TimeSpan -Days 3650)
        $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
            -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -MultipleInstances IgnoreNew `
            -ExecutionTimeLimit (New-TimeSpan -Days 3650)
        Register-ScheduledTask -TaskName $taskName -Action $action `
            -Trigger $trigger -Settings $settings -Force | Out-Null
        Write-Host "Tarea '$taskName' creada (latido cada 5 min; revive el bot si muere)."
    }

    "arrancar" {
        Start-ScheduledTask -TaskName $taskName
        Start-Sleep 3
        Write-Host "Tarea '$taskName' arrancada. Log: $repo\logs\telegram_bot.log"
    }

    "activar" {
        Enable-ScheduledTask -TaskName $taskName | Out-Null
        Write-Host "Tarea '$taskName' activada."
    }

    "desactivar" {
        Disable-ScheduledTask -TaskName $taskName | Out-Null
        Write-Host "Tarea '$taskName' desactivada."
    }

    "detener" {
        # Para la instancia que corre (para poder lanzar el bot a mano
        # en una terminal visible sin conflicto de getUpdates).
        Stop-ScheduledTask -TaskName $taskName
        Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
            Where-Object { $_.CommandLine -match 'telegram_bot' } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
        Write-Host "Bot detenido. Para volver al modo servicio: -Accion arrancar"
    }

    "desinstalar" {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Tarea '$taskName' eliminada."
    }

    "estado" {
        $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if ($null -eq $task) {
            Write-Host "Tarea '$taskName' no existe."
        } else {
            $info = $task | Get-ScheduledTaskInfo
            Write-Host "Estado  : $($task.State)"
            Write-Host "Ultima  : $($info.LastRunTime) (resultado: $($info.LastTaskResult))"
        }
    }
}
