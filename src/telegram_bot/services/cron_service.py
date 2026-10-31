"""Servicio del cron para los comandos Go/Kill/Status de Yadira (REQ-105).

El flujo diario vive en src/scheduler/runner.py: la tarea de Windows lo
dispara cada 30 min con --check (corre lo vencido) y existe --forzar
USUARIO para correrlo ya. El runner toma el candado data/scheduler.lock
con el PID del proceso adentro (REQ-060), que es la fuente de verdad de
"esta corriendo" para los tres comandos:

 - Go    -> arranca `runner --forzar yadira` DESPRENDIDO (como lo hace
            el Programador de Tareas: sobrevive a esta conversacion).
            Si ya corre, no lanza una segunda cadena.
 - Kill  -> mata el ARBOL del runner (taskkill /T: runner + paso en
            curso + Selenium) y limpia el candado que queda huerfano.
 - Status-> reporte chico: corre o no, PID, ultimo paso visto en
            logs/scheduler.log y ultima actividad del cron.

Este modulo es SOLO del bot: el flujo en ejecucion no lo importa.
"""

from __future__ import annotations

import logging
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

from src.core.rutas import DATA_DIR, LOGS_DIR, ROOT

logger = logging.getLogger(__name__)

RUTA_LOCK = DATA_DIR / "scheduler.lock"
LOG_SCHEDULER = LOGS_DIR / "scheduler.log"
USUARIO_DEFAULT = "yadira"

_PY = ROOT / "venv" / "Scripts" / "python.exe"
if not _PY.exists():  # compatibilidad si algun dia corre en Linux
    _PY = ROOT / "venv" / "bin" / "python"

_RX_PASO = re.compile(r"paso \d+/\d+:")
_RX_ACTIVIDAD = re.compile(
    r"inicio de cadena|cadena completa OK|FALLO en paso|check: nada vencido"
)


def pid_vivo(pid: int) -> bool:
    """True si el proceso Windows con ese PID sigue corriendo.

    No basta OpenProcess: un proceso TERMINADO cuyo objeto sigue
    referenciado (el Task Scheduler retiene el handle) se abre igual y
    haria parecer vivo un lock muerto — caso real 2026-10-11. Se
    consulta el codigo de salida: mientras corre es STILL_ACTIVE (259).
    """
    try:
        import ctypes

        k32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid)
        if not handle:
            return False
        try:
            codigo = ctypes.c_ulong()
            if not k32.GetExitCodeProcess(handle, ctypes.byref(codigo)):
                return False
            return codigo.value == STILL_ACTIVE
        finally:
            k32.CloseHandle(handle)
    except Exception:
        return False


def _leer_pid(lock: Path) -> int | None:
    try:
        return int(lock.read_text(encoding="utf-8").strip() or 0) or None
    except (OSError, ValueError):
        return None


def _ts_de_linea(linea: str) -> float | None:
    try:
        return datetime.strptime(linea[:19], "%Y-%m-%d %H:%M:%S").timestamp()
    except ValueError:
        return None


def _lineas_recientes(log: Path, desde_ts: float | None, cola: int = 400) -> list[str]:
    try:
        with log.open("r", encoding="utf-8", errors="replace") as fh:
            lineas = fh.readlines()[-cola:]
    except OSError:
        return []
    if desde_ts is None:
        return [ln.rstrip("\n") for ln in lineas]
    return [
        ln.rstrip("\n")
        for ln in lineas
        if (ts := _ts_de_linea(ln)) is not None and ts >= desde_ts - 1
    ]


def paso_en_curso(lock_mtime: float, log: Path | None = None) -> str | None:
    """La ultima linea 'paso N/M: ...' del log DENTRO de esta corrida.

    Se acota por el mtime del candado para no reportar el paso de una
    corrida anterior que siga en el log.
    """
    for linea in reversed(_lineas_recientes(log or LOG_SCHEDULER, lock_mtime)):
        if _RX_PASO.search(linea):
            return linea.strip()
    return None


def ultima_actividad(log: Path | None = None) -> str | None:
    """La ultima linea relevante del cron (inicio/completa/fallo/check)."""
    for linea in reversed(_lineas_recientes(log or LOG_SCHEDULER, None, cola=200)):
        if _RX_ACTIVIDAD.search(linea):
            return linea.strip()
    return None


def estado_cron() -> dict:
    """{corriendo, huerfano, pid, paso} segun el candado del runner."""
    if not RUTA_LOCK.exists():
        return {"corriendo": False, "huerfano": False, "pid": None, "paso": None}
    pid = _leer_pid(RUTA_LOCK)
    mtime = RUTA_LOCK.stat().st_mtime
    if not pid or not pid_vivo(pid):
        # Candado huerfano: el runner murio sin limpiar (p. ej. Kill de
        # Windows o un apagon). No esta corriendo.
        return {"corriendo": False, "huerfano": True, "pid": pid, "paso": None}
    return {
        "corriendo": True,
        "huerfano": False,
        "pid": pid,
        "paso": paso_en_curso(mtime),
    }


def arrancar_cron(usuario: str = USUARIO_DEFAULT) -> tuple[bool, str]:
    """Go: lanza la cadena ya, desprendida. (corriendo, detalle)."""
    est = estado_cron()
    if est["corriendo"]:
        return False, f"ya corre (PID {est['pid']})"
    if est["huerfano"]:
        RUTA_LOCK.unlink(missing_ok=True)  # si no, el runner ve el lock y sale

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_go = LOGS_DIR / f"cron_go_{ts}.log"
    flags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200
    )
    with log_go.open("ab") as fh:
        proc = subprocess.Popen(
            [str(_PY), "-m", "src.scheduler.runner", "--forzar", usuario],
            cwd=str(ROOT),
            stdout=fh,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
        )
    logger.info("Go: runner lanzado (PID %s, log %s)", proc.pid, log_go.name)

    fin = time.time() + 15
    while time.time() < fin:
        if proc.poll() is not None:
            return (
                False,
                f"el proceso salio de inmediato (codigo {proc.returncode}); "
                f"revisar {log_go.name}",
            )
        est = estado_cron()
        if est["corriendo"]:
            return True, f"corriendo (PID {est['pid']})"
        time.sleep(1)
    if proc.poll() is not None:
        return (
            False,
            f"el proceso salio sin tomar el candado (codigo {proc.returncode}); "
            f"revisar {log_go.name}",
        )
    return True, f"lanzado (PID {proc.pid}), aun tomando el candado"


def matar_cron() -> tuple[bool, str]:
    """Kill: mata el arbol del runner y limpia el candado."""
    est = estado_cron()
    if not est["corriendo"]:
        if est["huerfano"]:
            RUTA_LOCK.unlink(missing_ok=True)
            return True, "no corria; candado huerfano limpiado"
        return False, "no corre"
    pid = est["pid"]
    assert pid is not None
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        logger.warning("Kill: taskkill fallo: %s", e)
    fin = time.time() + 8
    while pid_vivo(pid) and time.time() < fin:
        time.sleep(0.5)
    if pid_vivo(pid):
        return False, f"no pude matar el proceso (PID {pid})"
    RUTA_LOCK.unlink(missing_ok=True)
    return True, f"flujo detenido (PID {pid}) y candado limpiado"


def _cortar(linea: str, maximo: int = 120) -> str:
    return linea if len(linea) <= maximo else linea[: maximo - 1] + "…"


def texto_status() -> str:
    """El reporte chito de Status (texto plano para Telegram)."""
    est = estado_cron()
    if est["corriendo"]:
        msg = f"El flujo diario ESTA corriendo (PID {est['pid']})."
        if est["paso"]:
            msg += f"\nUltimo paso: {_cortar(est['paso'])}"
        msg += "\nEscribeme Kill si necesitas detenerlo."
        return msg
    if est["huerfano"]:
        return (
            f"El flujo diario NO esta corriendo (encontre un candado huerfano "
            f"del PID {est['pid']}, ya muerto). Escribeme Go para arrancarlo."
        )
    msg = "El flujo diario NO esta corriendo."
    ultima = ultima_actividad()
    if ultima:
        msg += f"\nUltima actividad del cron: {_cortar(ultima)}"
    msg += "\nEscribeme Go para arrancarlo."
    return msg
