"""CLI del paso 2b: consolidar examenes de un paciente via vision.

Uso:
    python -m src.tools.consolidar_examenes --paciente "Nombre Apellido" [--fecha dd-mm-yyyy]

Modo conciliacion (REQ-102, paso diario antes de Mortadelo):
    python -m src.tools.consolidar_examenes --pendientes
    Consolida TODO crudo procesable que no aparezca en ningun md
    (archivos_origen). Best-effort: fallos por paciente se loguean y
    SIEMPRE sale 0 para no detener la cadena diaria.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from src.examenes.conciliar import conciliar_pendientes
from src.examenes.consolidar import consolidar_examenes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="consolidar_examenes",
        description=(
            "Paso 2b (opt-in): transcribe las fotos crudas de un paciente "
            "con la API de vision de z.ai y consolida exam_<pac>_<fecha>.md. "
            "Con --pendientes consolida todo crudo sin md (REQ-102)."
        ),
    )
    parser.add_argument(
        "--paciente",
        default=None,
        help="Nombre del paciente (puede ser parcial NO: usar el mismo con que se archivo en 2a)",
    )
    parser.add_argument(
        "--fecha",
        default=None,
        help="Fecha de atencion dd-mm-yyyy (default: la de los archivos crudos)",
    )
    parser.add_argument(
        "--pendientes",
        action="store_true",
        help=(
            "Modo conciliacion diaria: escanea examenes_crudos y consolida "
            "todo crudo que no este en ningun exam_*.md (REQ-102). "
            "Incompatible con --paciente."
        ),
    )
    args = parser.parse_args(argv)

    if args.pendientes:
        if args.paciente or args.fecha:
            parser.error("--pendientes no lleva --paciente ni --fecha")
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        resumen = conciliar_pendientes(logger=logging.getLogger("conciliar_examenes"))
        print(json.dumps(resumen, ensure_ascii=False, indent=2))
        # Best-effort por diseño: fallos por paciente quedaron logueados;
        # la cadena diaria NO se detiene por un OCR caido.
        return 0

    if not args.paciente:
        parser.error("se requiere --paciente (o --pendientes)")

    resultado = consolidar_examenes(paciente=args.paciente, fecha=args.fecha)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0 if resultado["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
