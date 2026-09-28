"""Corre el flujo diario completo (REQ-008) en el orden real 4 -> 5 -> 3 -> 6 -> 7 -> 8.

Uso:
    python flujo_diario.py            (pide confirmacion antes de abrir Chrome)
    python flujo_diario.py -y         (sin confirmacion)
    python flujo_diario.py --solo 5   (corre SOLO el paso con ese numero, p.ej. 5)

Consola: la salida de cada paso se FILTRA para que se lea lo que esta
pasando (progreso, warnings, errores) sin stacktraces ni ruido de
logging. La salida COMPLETA y sin filtrar de cada corrida queda en
logs/flujo_diario_<timestamp>.log para diagnostico.

Importante:
- Los pasos (4), (3) y (8) abren Chrome con login a Rayen: el operador
  debe estar presente al inicio para validar la sesion.
- Sale en el primer paso que falle (semantica &&). Excepcion: si
  Mortadelo (7) termina con exit parcial (codigo 1), el flujo CONTINUA
  al paso 8 con las fichas que alcanzaron a generarse (misma tolerancia
  que el cron).
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = ROOT / "venv" / "Scripts" / "python.exe"
if not PY.exists():  # fallback por compatibilidad si algun dia corre en Linux
    PY = ROOT / "venv" / "bin" / "python"
LOGS_DIR = ROOT / "logs"

PASOS = [
    (
        "4",
        "Actualizar DB del mes (login Rayen)",
        ["-m", "src.analysis.actualizar_mes_actual", "yadira"],
    ),
    ("5", "Informe base de fichas abiertas", ["-m", "src.analysis.informe_fichas_abiertas"]),
    (
        "3",
        "Scrapear fichas del informe (login Rayen)",
        ["-m", "src.tools.crear_notas_clinicas", "--todos", "--user", "yadira"],
    ),
    ("6", "Enriquecer el informe", ["-m", "src.analysis.enriquecer_informe"]),
    (
        "7",
        "Mortadelo: fichas completas + informes de trazabilidad (LLM)",
        ["-m", "src.tools.mortadelo", "--todos"],
    ),
    (
        "8",
        "Cargar fichas generadas en Rayen (login Rayen, Guardar automatico)",
        ["-m", "src.tools.cargar_ficha", "--todos", "--user", "yadira"],
    ),
    (
        "A",
        "Archivar pacientes cerrados a OneDrive/archivados/<mes> (REQ-097)",
        ["-m", "src.tools.archivar_fichas"],
    ),
]

# ---- Filtro de consola (todo lo suprimido va igual al log de corrida) ----

# Prefijos estandar de logging que se quitan de la consola:
#   "2026-09-27 02:44:25 - login_automation - INFO - "   (runner)
#   "2026-09-27 23:10:39,343 [INFO] [crear_notas] "      (CLIs)
TS_RE = re.compile(
    r"^(?:\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:,\d+)? - \S+ - (INFO|WARNING|ERROR) - "
    r"|\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+ \[(INFO|WARNING|ERROR)\] )"
)
# Ruido repetitivo de navegacion y stacktraces de chromedriver.
RUIDO_RE = re.compile(
    r"No se detect[oó] modal"
    r"|Esperando input de fecha"
    r"|Fecha [\d-]+ ingresada"
    r"|Tabla ordenada"
    r"|Screenshot: "
    r"|Modal 'Cargando'"
    r"|Menu lateral abierto"
    r"|Navegando a https"
    r"|Iniciando instancia de Google Chrome"
    r"|chromedriver!"
    r"|KERNEL32!"
    r"|ntdll!"
    r"|Stacktrace:"
    r"|For documentation on this error"
    r"|^\s*\(Session info:"
    r"|^\s*Message: no such element"  # el ERROR original ya se muestra
)
# Filas del volcado del informe base (todas '(-)' en esa etapa: ruido).
FILA_INFORME_RE = re.compile(r"^\d{2}-\d{2}-\d{4}\s{2,}")
SEPARADOR_RE = re.compile(r"^[=\-]{20,}\s*$")


def clasificar_linea(cruda: str) -> str | None:
    """Decide que mostrar en consola. None = suprimir (solo log)."""
    linea = cruda.rstrip("\n")
    if not linea.strip():
        return None
    if RUIDO_RE.search(linea):
        return None
    m = TS_RE.match(linea)
    if m:
        nivel = m.group(1) or m.group(2)
        msg = linea[m.end():]
        if nivel == "INFO":
            return msg
        prefijo = "[!]" if nivel == "WARNING" else "[X]"
        return f"{prefijo} {msg}"
    if FILA_INFORME_RE.match(linea) or SEPARADOR_RE.match(linea):
        return None
    return linea


def _formatear_duracion(seg: float) -> str:
    if seg >= 60:
        return f"{int(seg // 60)}m {int(seg % 60):02d}s"
    return f"{seg:.0f}s"


def correr_paso(
    i: int,
    n: int,
    num: str,
    desc: str,
    args: list[str],
    log_run,
) -> int:
    print("─" * 64)
    print(f"[{i}/{n}] PASO {num} · {desc}")
    print("─" * 64)
    t0 = time.monotonic()
    # PYTHONIOENCODING: con stdout=PIPE los hijos no ven consola y usan
    # cp1252 -> mueren con UnicodeEncodeError al imprimir '→' (mes.py).
    # Mismo fix que usa el runner del cron.
    import os

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.Popen(
        [str(PY), *args],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
    )
    assert proc.stdout is not None
    for cruda in proc.stdout:
        log_run.write(cruda)
        visible = clasificar_linea(cruda)
        if visible is not None:
            print(f"   {visible}", flush=True)
    codigo = proc.wait()
    dur = _formatear_duracion(time.monotonic() - t0)
    simbolo = "OK" if codigo == 0 else f"FALLO (codigo {codigo})"
    print(f"\n   >> paso {num}: {simbolo} · {dur}\n")
    return codigo


def _extraer_solo(argv: list[str]) -> str | None:
    """Soporta '--solo 5' y '--solo=5'."""
    for idx, a in enumerate(argv):
        if a == "--solo" and idx + 1 < len(argv):
            return argv[idx + 1]
        if a.startswith("--solo="):
            return a.split("=", 1)[1]
    return None


def main() -> int:
    solo = _extraer_solo(sys.argv[1:])
    pasos = PASOS
    if solo:
        pasos = [p for p in PASOS if p[0] == solo]
        if not pasos:
            print(f"No existe el paso '{solo}'. Validos: {', '.join(p[0] for p in PASOS)}")
            return 2
    confirmado = any(a in ("-y", "--yes") for a in sys.argv[1:])

    print("=" * 64)
    print(f"FLUJO DIARIO — {datetime.now():%d-%m-%Y %H:%M}")
    print("=" * 64)
    cadena = " -> ".join(f"({num})" for num, _, _ in pasos)
    print(f"Pasos: {cadena}")
    print("   (4)(3)(8) abren Chrome con login a Rayen")

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ruta_log = LOGS_DIR / f"flujo_diario_{datetime.now():%Y%m%d_%H%M%S}.log"

    if not confirmado:
        respuesta = (
            input("\nEsto abrira Chrome para login en Rayen. ¿Continuar? [s/N]: ").strip().lower()
        )
        if respuesta not in ("s", "si", "sí", "y", "yes"):
            print("Cancelado.")
            return 1

    t_total = time.monotonic()
    duraciones: list[tuple[str, str, int, str]] = []
    fallo: int | None = None
    with ruta_log.open("w", encoding="utf-8") as log_run:
        for i, (num, desc, args) in enumerate(pasos, 1):
            codigo = correr_paso(i, len(pasos), num, desc, args, log_run)
            dur = _formatear_duracion(time.monotonic() - t_total)
            duraciones.append((num, desc, codigo, dur))
            if codigo != 0:
                # Tolerancia del cron: exit 1 de Mortadelo (7) = exito
                # parcial -> continuar al paso 8 con lo generado.
                if num == "7" and codigo == 1 and i < len(pasos):
                    print("   [AVISO] Mortadelo termino parcial; se continua con las fichas generadas.")
                    continue
                # Paso 8 fallido: igual archivar (paso A), que solo
                # depende del informe (pasos 5/6), no de la carga.
                if num == "8" and i < len(pasos):
                    print("   [AVISO] El paso 8 fallo; se archivan igual los cerrados (paso A).")
                    fallo = codigo
                    continue
                fallo = codigo
                break

    print("=" * 64)
    print("RESUMEN")
    print("=" * 64)
    for num, _desc, codigo, _dur in duraciones:
        estado = "OK" if codigo == 0 else f"FALLO ({codigo})"
        print(f"   paso {num}: {estado}")
    print(f"   Duracion total: {_formatear_duracion(time.monotonic() - t_total)}")
    print(f"   Log completo de la corrida: {ruta_log}")
    if fallo is not None:
        print(f"\n[FALLO] El flujo se detuvo (codigo {fallo}). Los pasos previos ya estan hechos.")
        return fallo
    print("\n[OK] Flujo completo terminado.")
    print("   Informe: OneDrive/Login-Automation/informe_fichas_abiertas_<mes>.txt")
    print("   Notas: data/notas_clinicas/ · Info: data/info_paciente/")
    print("   Anamnesis: OneDrive/anamnesis/ · Fichas: OneDrive/fichas_generadas/")
    print("   Trazabilidad: OneDrive/informes_trazabilidad/ · Fichas cargadas en Rayen (paso 8)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
