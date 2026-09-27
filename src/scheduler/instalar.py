"""Instalacion del scheduler en el Programador de Tareas de Windows.

Crea UNA tarea que dispara cada 30 minutos (todo el dia, todos los dias):
es el runner quien decide con config/calendario.json si corresponde
correr. Ventajas: cambiar el calendario no toca la tarea; si el PC estaba
apagado a la hora exacta, corre en el primer disparo posterior
(StartWhenAvailable); y una sola cosa que instalar/desinstalar.

Uso:
    python -m src.scheduler.instalar            # crea la tarea (queda DESACTIVADA)
    python -m src.scheduler.instalar --activar   # la habilita
    python -m src.scheduler.instalar --desactivar
    python -m src.scheduler.instalar --desinstalar
    python -m src.scheduler.instalar --estado    # muestra como esta

Queda DESACTIVADA a proposito: el operador la habilita cuando el PC de
turno este listo (venv instalado, users.json/.env con credenciales).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):  # script directo: bootstrap para `from src...`
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.core.rutas import ROOT

NOMBRE_TAREA = "LoginAutomation-FlujoDiario"
SCRIPT_PS1 = ROOT / "scripts" / "registrar_scheduler.ps1"


def _ps(accion: str) -> int:
    """Ejecuta el script PowerShell de registro con la accion pedida."""
    if not SCRIPT_PS1.exists():
        print(f"No existe {SCRIPT_PS1}", file=sys.stderr)
        return 2
    resultado = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT_PS1),
            "-Accion",
            accion,
        ],
        cwd=str(ROOT),
    )
    return resultado.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="instalar", description="Tarea de Windows del scheduler")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--instalar", action="store_true", help="crea la tarea (queda desactivada)")
    grupo.add_argument("--activar", action="store_true", help="habilita la tarea")
    grupo.add_argument("--desactivar", action="store_true", help="deshabilita la tarea (no borra nada)")
    grupo.add_argument("--desinstalar", action="store_true", help="borra la tarea")
    grupo.add_argument("--estado", action="store_true", help="muestra el estado de la tarea")
    args = parser.parse_args(argv)

    if args.instalar:
        codigo = _ps("instalar")
        if codigo == 0:
            print(
                "\nTarea creada pero DESACTIVADA. Cuando quieras dejarla corriendo:\n"
                "  python -m src.scheduler.instalar --activar\n"
                "Verificacion rapida sin correr el flujo:\n"
                "  python -m src.scheduler.runner --listar"
            )
        return codigo
    if args.activar:
        return _ps("activar")
    if args.desactivar:
        return _ps("desactivar")
    if args.desinstalar:
        return _ps("desinstalar")
    return _ps("estado")


if __name__ == "__main__":
    sys.exit(main())
