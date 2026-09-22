# Registrar/operar la tarea de Windows del bot Rubicita (paso 2a).
# Invocado por el operador o documentado en INSTALACION. Requiere que
# el repo este instalado en C:\login-automation-bot (worktree de la
# rama feat/telegram-bot-rubicita) con su venv.
#
# La tarea arranca el bot al iniciar sesion (pythonw, sin ventana) y
# se puede arrancar/detener a mano sin cerrar sesion.
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("instalar", "activar", "desactivar", "desinstalar", "estado", "arrancar")]
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
        # Al iniciar sesion + cada 5 min por si muere (StartWhenAvailable
        # + MultipleInstances IgnoreNew evita duplicados).
        $action = New-ScheduledTaskAction -Execute $pythonw `
            -Argument "-m src.telegram_bot.app" `
            -WorkingDirectory $repo
        $trigger = New-ScheduledTaskTrigger -AtLogOn
        $repetir = New-ScheduledTaskTrigger -Once -At (Get-Date) `
            -RepetitionInterval (New-TimeSpan -Minutes 5) `
            -RepetitionDuration (New-TimeSpan -Days 3650)
        $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
            -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -MultipleInstances IgnoreNew `
            -ExecutionTimeLimit (New-TimeSpan -Days 3650)
        Register-ScheduledTask -TaskName $taskName -Action $action `
            -Trigger $trigger, $repetir -Settings $settings -Force | Out-Null
        Write-Host "Tarea '$taskName' creada (arranque al iniciar sesion + latido cada 5 min)."
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
