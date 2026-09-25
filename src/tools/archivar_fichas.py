"""CLI del archivo de fichas (REQ-082): mueve a `fichas archivadas` las
fichas generadas (paso 7) que YA NO estan en el informe de fichas
abiertas del mes (pacientes cerrados).

Semantica:
- La carpeta activa (`FICHAS_GENERADAS_DIR`) queda con solo las fichas
  de pacientes del informe.
- Las cerradas se MUEVEN a `FICHAS_ARCHIVADAS_DIR` (historial en
  OneDrive; nunca se borra nada). Colisiones -> sufijo _v2, _v3...
- Si el informe no existe o no se puede leer, NO se mueve nada
  (guardia: sin informe fresco no hay criterio de cierre).

Uso:
    python -m src.tools.archivar_fichas            # mueve
    python -m src.tools.archivar_fichas --dry-run  # solo lista
"""

from __future__ import annotations

import argparse
import contextlib
import re
import shutil
import sys
from pathlib import Path

with contextlib.suppress(AttributeError, OSError):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from src.core.nombres import safe_filename
from src.core.rutas import (
    FICHAS_ARCHIVADAS_DIR,
    FICHAS_GENERADAS_DIR,
    informe_mes_actual_path,
)
from src.informes.parser import parsear_pacientes_objetivo

# ficha_<safe>_<dd-mm-yyyy>.md — el nombre del paciente lleva guiones
# bajos internos, la fecha es el ultimo segmento _dd-mm-yyyy.
_FICHA_RE = re.compile(r"^ficha_(?P<paciente>.+)_(?P<fecha>\d{2}-\d{2}-\d{4})\.md$")


def _resolver_sin_colision(destino_dir: Path, nombre: str) -> Path:
    candidato = destino_dir / nombre
    if not candidato.exists():
        return candidato
    stem, suffix, n = candidato.stem, candidato.suffix, 2
    while True:
        nuevo = destino_dir / f"{stem}_v{n}{suffix}"
        if not nuevo.exists():
            return nuevo
        n += 1


def fichas_cerradas(
    informe_path: Path, origen_dir: Path = FICHAS_GENERADAS_DIR
) -> list[Path]:
    """Fichas generadas cuyo (paciente, fecha) NO esta en el informe."""
    if not informe_path.exists():
        return []
    try:
        pacientes = parsear_pacientes_objetivo(informe_path)
    except Exception:
        return []
    abiertas = {
        (safe_filename(p.nombre), p.fecha) for p in pacientes
    }
    cerradas: list[Path] = []
    for ficha in sorted(origen_dir.glob("ficha_*.md")):
        m = _FICHA_RE.match(ficha.name)
        if not m:
            continue
        if (m.group("paciente"), m.group("fecha")) not in abiertas:
            cerradas.append(ficha)
    return cerradas


def archivar_fichas_cerradas(
    logger=None,
    informe_path: Path | None = None,
    origen_dir: Path = FICHAS_GENERADAS_DIR,
    destino_dir: Path = FICHAS_ARCHIVADAS_DIR,
) -> list[tuple[str, str]]:
    """Mueve las fichas cerradas al archivo. Devuelve [(origen, destino)]."""
    informe = informe_path or informe_mes_actual_path()
    cerradas = fichas_cerradas(informe, origen_dir)
    if not cerradas:
        if logger:
            logger.info("[archivar_fichas] nada para archivar (informe %s)", informe.name)
        return []
    destino_dir.mkdir(parents=True, exist_ok=True)
    movidas: list[tuple[str, str]] = []
    for ficha in cerradas:
        destino = _resolver_sin_colision(destino_dir, ficha.name)
        try:
            shutil.move(str(ficha), str(destino))
            movidas.append((ficha.name, destino.name))
            if logger:
                logger.info("[archivar_fichas] %s -> %s", ficha.name, destino.name)
        except OSError as e:
            if logger:
                logger.warning("[archivar_fichas] no se pudo mover %s: %s", ficha.name, e)
    if logger:
        logger.info(
            "[archivar_fichas] %d ficha(s) archivada(s), %d quedan activas",
            len(movidas),
            len(list(origen_dir.glob("ficha_*.md"))),
        )
    return movidas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="archivar_fichas",
        description=(
            "Mueve a 'fichas archivadas' las fichas generadas que ya no "
            "estan en el informe de fichas abiertas del mes (REQ-082)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="lista las fichas que se moverian, sin mover nada",
    )
    parser.add_argument("--informe", type=Path, default=None)
    args = parser.parse_args(argv)

    with contextlib.suppress(AttributeError):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    informe = args.informe or informe_mes_actual_path()
    cerradas = fichas_cerradas(informe, FICHAS_GENERADAS_DIR)
    if not cerradas:
        print(f"[archivar_fichas] nada para archivar (informe: {informe.name})")
        return 0
    print(f"[archivar_fichas] {len(cerradas)} ficha(s) cerrada(s):")
    for ficha in cerradas:
        if args.dry_run:
            print(f"  (se moveria) {ficha.name}")
        else:
            destino = _resolver_sin_colision(FICHAS_ARCHIVADAS_DIR, ficha.name)
            try:
                shutil.move(str(ficha), str(destino))
                print(f"  {ficha.name} -> {destino.name}")
            except OSError as e:
                print(f"  ERROR moviendo {ficha.name}: {e}")
    return 0
if __name__ == "__main__":
    sys.exit(main())
