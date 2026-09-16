"""Limpia capturas de pantalla de diagnostico despues de una corrida exitosa.

Las screenshots + HTML que `_capture_after_click` y `_capture_error` escriben
durante el flujo se acumulan en `logs/screenshots/` (gitignored). En una
corrida exitosa NO aportan valor (no hay nada que debuggear), asi que este
script las borra.

Uso:
    python -m src.tools.limpiar_screenshots             # borra TODAS
    python -m src.tools.limpiar_screenshots --older 60 # borra > 60 min

Cuando usar `--older N`: util si queres preservar capturas de la corrida
actual (por si necesitas debuggear en los proximos minutos) y borrar
solo las corridas mas viejas.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCREENSHOTS_DIR = ROOT / "logs" / "screenshots"


def limpiar(minutes: int | None = None) -> int:
    """Borra archivos en logs/screenshots/. Si `minutes` se da, solo los mas
    viejos que ese threshold. Devuelve la cantidad borrada.
    """
    if not SCREENSHOTS_DIR.exists():
        return 0

    patrones = ("step_*.png", "error_*.png", "error_*.html")
    archivos = []
    for patron in patrones:
        archivos.extend(SCREENSHOTS_DIR.glob(patron))

    if minutes is not None:
        ahora = time.time()
        umbral = ahora - minutes * 60
        archivos_filtrados = []
        for f in archivos:
            try:
                mtime = f.stat().st_mtime
            except OSError:
                continue
            if mtime < umbral:
                archivos_filtrados.append(f)
        archivos = archivos_filtrados

    borrados = 0
    for f in archivos:
        try:
            f.unlink()
            borrados += 1
        except OSError as e:
            logging.warning(f"No se pudo borrar {f}: {e}")

    return borrados


def main() -> int:
    p = argparse.ArgumentParser(
        description="Borra capturas de pantalla de logs/screenshots/."
    )
    p.add_argument(
        "--older",
        type=int,
        default=None,
        metavar="MIN",
        help="Solo borra archivos mas viejos que MIN minutos. Default: borra todos.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra cuantos borraria sin tocar nada.",
    )
    args = p.parse_args()

    if args.dry_run:
        if not SCREENSHOTS_DIR.exists():
            print(f"[dry-run] {SCREENSHOTS_DIR} no existe")
            return 0
        patrones = ("step_*.png", "error_*.png", "error_*.html")
        total = 0
        for patron in patrones:
            archivos = list(SCREENSHOTS_DIR.glob(patron))
            if args.older is not None:
                ahora = time.time()
                umbral = ahora - args.older * 60
                archivos = [f for f in archivos if f.stat().st_mtime < umbral]
            total += len(archivos)
        print(f"[dry-run] {total} archivos a borrar en {SCREENSHOTS_DIR}")
        return 0

    borrados = limpiar(minutes=args.older)
    target = "todos" if args.older is None else f"> {args.older} min"
    print(f"[limpiar_screenshots] {borrados} archivos borrados ({target}) de {SCREENSHOTS_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())