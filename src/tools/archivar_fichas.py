"""CLI del archivo de productos cerrados (REQ-082/088/097).

Mueve a archivados/<MM-AAAA>/ los productos de pacientes que YA NO
estan en el informe de fichas abiertas del mes (pacientes cerrados).
Productos: notas clinicas, info paciente, anamnesis, fichas generadas
e informes de trazabilidad — las carpetas activas quedan SOLO con
pacientes del informe (lectura facil para Yadira).

Sistema de archivo (REQ-097): el archivo vive en OneDrive
(``ARCHIVADOS_DIR``), una subcarpeta PLANA por mes tomado del informe
(``09-2026``); los nombres de archivo ya llevan prefijo de producto +
paciente + fecha, asi que el mes no necesita subdivision.

Semantica:
- Los archivos cerrados se MUEVEN (nunca se borra nada; colisiones ->
  _v2, _v3...).
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
    ANAMNESIS_DIR,
    ARCHIVADOS_DIR,
    FICHAS_GENERADAS_DIR,
    INFO_PACIENTE_DIR,
    INFORMES_TRAZABILIDAD_DIR,
    NOTAS_DIR,
    informe_mes_actual_path,
)
from src.informes.parser import parsear_pacientes_objetivo

# (nombre producto, carpeta origen, prefijo del archivo). El nombre del
# paciente + la fecha van despues del prefijo: <prefijo><safe>_<dd-mm-yyyy>.md
PRODUCTOS: list[tuple[str, Path, str]] = [
    ("notas_clinicas", NOTAS_DIR, ""),
    ("info_paciente", INFO_PACIENTE_DIR, "info_"),
    ("anamnesis", ANAMNESIS_DIR, "anam_"),
    ("fichas_generadas", FICHAS_GENERADAS_DIR, "ficha_"),
    ("informes_trazabilidad", INFORMES_TRAZABILIDAD_DIR, "informe_trazabilidad_"),
]


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


def _abiertas_del_informe(informe_path: Path) -> set[tuple[str, str]] | None:
    """(safe_nombre, fecha) de los pacientes del informe; None si invalido."""
    if not informe_path.exists():
        return None
    try:
        pacientes = parsear_pacientes_objetivo(informe_path)
    except Exception:
        return None
    return {(safe_filename(p.nombre), p.fecha) for p in pacientes}


def cerrados_por_producto(
    informe_path: Path, dirs_override: dict[str, Path] | None = None
) -> dict[str, list[Path]]:
    """Por producto: archivos cuyo (paciente, fecha) NO esta en el informe.

    dirs_override: {producto: dir} para tests; default = rutas reales.
    """
    abiertas = _abiertas_del_informe(informe_path)
    vacio: dict[str, list[Path]] = {nombre: [] for nombre, _d, _p in PRODUCTOS}
    if abiertas is None:
        return vacio

    override = dirs_override or {}
    resultado: dict[str, list[Path]] = {}
    for nombre, dir_real, prefijo in PRODUCTOS:
        dir_origen = override.get(nombre, dir_real)
        if not dir_origen.exists():
            resultado[nombre] = []
            continue
        patron = re.escape(prefijo) + r"(.+)_(\d{2}-\d{2}-\d{4})\.md$"
        cerrados: list[Path] = []
        for archivo in sorted(dir_origen.glob(f"{prefijo}*.md")):
            m = re.match(patron, archivo.name)
            if not m:
                continue  # nombre sin fecha reconocible: no se toca
            if (m.group(1), m.group(2)) not in abiertas:
                cerrados.append(archivo)
        resultado[nombre] = cerrados
    return resultado


def _mes_del_informe(informe_path: Path) -> str:
    """'09-2026' del nombre del informe; fallback = mes actual."""
    m = re.search(r"_(\d{2}-\d{4})(?:\.txt)?$", informe_path.stem)
    if m:
        return m.group(1)
    from datetime import date

    return date.today().strftime("%m-%Y")


def archivar_cerrados(
    logger=None,
    informe_path: Path | None = None,
    destino_dir: Path = ARCHIVADOS_DIR,
    dirs_override: dict[str, Path] | None = None,
) -> list[tuple[str, str]]:
    """Mueve TODOS los productos cerrados a archivados/<MM-AAAA>/.

    `destino_dir` es la RAIZ del archivo; la subcarpeta del mes sale
    del nombre del informe (REQ-097).

    Returns:
        [(nombre_producto, nombre_archivo), ...] de lo movido.
    """
    informe = informe_path or informe_mes_actual_path()
    por_producto = cerrados_por_producto(informe, dirs_override)
    movidas: list[tuple[str, str]] = []
    if sum(len(v) for v in por_producto.values()) == 0:
        if logger:
            logger.info("[archivar] nada para archivar (informe %s)", informe.name)
        return movidas
    destino_mes = destino_dir / _mes_del_informe(informe)
    destino_mes.mkdir(parents=True, exist_ok=True)
    for nombre, cerrados in por_producto.items():
        for archivo in cerrados:
            destino = _resolver_sin_colision(destino_mes, archivo.name)
            try:
                shutil.move(str(archivo), str(destino))
                movidas.append((nombre, archivo.name))
                if logger:
                    logger.info("[archivar] %s: %s", nombre, destino.name)
            except OSError as e:
                if logger:
                    logger.warning("[archivar] no se pudo mover %s: %s", archivo.name, e)
    if logger:
        logger.info(
            "[archivar] %d archivo(s) archivado(s) en %s",
            len(movidas),
            destino_mes.name,
        )
    return movidas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="archivar_fichas",
        description=(
            "Mueve a 'archivados' los productos (notas, info, anamnesis, "
            "fichas, informes de trazabilidad) de pacientes que ya no "
            "estan en el informe de fichas abiertas (REQ-082/088)."
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="lista sin mover nada")
    parser.add_argument("--informe", type=Path, default=None)
    args = parser.parse_args(argv)

    informe = args.informe or informe_mes_actual_path()
    por_producto = cerrados_por_producto(informe)
    total = sum(len(v) for v in por_producto.values())
    if total == 0:
        print(f"[archivar] nada para archivar (informe: {informe.name})")
        return 0
    destino_mes = ARCHIVADOS_DIR / _mes_del_informe(informe)
    if not args.dry_run:
        destino_mes.mkdir(parents=True, exist_ok=True)
    for nombre, cerrados in por_producto.items():
        for archivo in cerrados:
            if args.dry_run:
                print(f"  ({nombre}) se moveria: {archivo.name}")
            else:
                destino = _resolver_sin_colision(destino_mes, archivo.name)
                try:
                    shutil.move(str(archivo), str(destino))
                    print(f"  ({nombre}) {archivo.name} -> {destino_mes.name}/{destino.name}")
                except OSError as e:
                    print(f"  ERROR moviendo {archivo.name}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
