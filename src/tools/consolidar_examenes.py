"""CLI del paso 2b: consolidar examenes de un paciente via vision z.ai.

Uso:
    python -m src.tools.consolidar_examenes --paciente "Nombre Apellido" [--fecha dd-mm-yyyy]
"""

from __future__ import annotations

import argparse
import json
import sys

from src.examenes.consolidar import consolidar_examenes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="consolidar_examenes",
        description=(
            "Paso 2b (opt-in): transcribe las fotos crudas de un paciente "
            "con la API de vision de z.ai y consolida exam_<pac>_<fecha>.md"
        ),
    )
    parser.add_argument(
        "--paciente",
        required=True,
        help="Nombre del paciente (puede ser parcial NO: usar el mismo con que se archivo en 2a)",
    )
    parser.add_argument(
        "--fecha",
        default=None,
        help="Fecha de atencion dd-mm-yyyy (default: la de los archivos crudos)",
    )
    args = parser.parse_args(argv)

    resultado = consolidar_examenes(paciente=args.paciente, fecha=args.fecha)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0 if resultado["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
