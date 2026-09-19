"""CLI del paso 7 (Mortadelo): ficha completa + informe de trazabilidad.

Uso:
    python -m src.tools.mortadelo --todos
    python -m src.tools.mortadelo --paciente "Nombre Apellido" --fecha dd-mm-yyyy

Corre DESPUES del paso 6 (lee el informe enriquecido). Motor: CLI de
opencode con cascada de modelos (REQ-055). Salidas:
    data/fichas_generadas/ficha_<pac>_<fecha>.md
    data/informes_trazabilidad/informe_trazabilidad_<pac>_<fecha>.md
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from src.core.rutas import informe_mes_actual_path
from src.mortadelo.generar import generar_fichas, generar_paciente


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mortadelo",
        description=(
            "Paso 7: genera la ficha completa (anamnesis con campos vacios "
            "llenados, sin trigger, con secciones pedidas) y el informe de "
            "trazabilidad por paciente del informe de fichas abiertas."
        ),
    )
    parser.add_argument(
        "--todos", action="store_true", help="Procesa todos los pacientes del informe."
    )
    parser.add_argument("--paciente", default=None, help="Modo 1 paciente.")
    parser.add_argument("--fecha", default=None, help="dd-mm-yyyy (modo 1 paciente).")
    parser.add_argument(
        "--informe",
        type=Path,
        default=None,
        help=f"Informe enriquecido (default: {informe_mes_actual_path().name}).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger("mortadelo")

    if not args.todos and not (args.paciente and args.fecha):
        parser.error("Usa --todos, o --paciente + --fecha.")

    if args.todos:
        informe = args.informe or informe_mes_actual_path()
        if not informe.exists():
            print(f"[mortadelo] ERROR: no existe el informe {informe}", file=sys.stderr)
            return 1
        resultados = generar_fichas(informe, logger=logger)
        ok = sum(1 for r in resultados if r.ok)
        print(f"\n[mortadelo] {ok}/{len(resultados)} pacientes completos.")
        for r in resultados:
            estado = "OK" if r.ok else f"ERROR: {r.error}"
            extras = f" (advertencias: {len(r.advertencias)})" if r.advertencias else ""
            print(f"  - {r.nombre} ({r.fecha}): {estado}{extras}")
        return 0 if ok == len(resultados) else 1

    resultado = generar_paciente(args.paciente, args.fecha, logger=logger)
    estado = "OK" if resultado.ok else f"ERROR: {resultado.error}"
    print(f"[mortadelo] {resultado.nombre} ({resultado.fecha}): {estado}")
    if resultado.ficha_path:
        print(f"  Ficha:   {resultado.ficha_path}")
    if resultado.informe_path:
        print(f"  Informe: {resultado.informe_path}")
    for adv in resultado.advertencias:
        print(f"  [advertencia] {adv}")
    return 0 if resultado.ok else 1


if __name__ == "__main__":
    sys.exit(main())
