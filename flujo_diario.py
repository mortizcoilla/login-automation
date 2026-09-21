"""Corre el flujo diario completo (REQ-008) en el orden real 4 -> 5 -> 3 -> 6 -> 7.

Uso:
    python flujo_diario.py          (pide confirmacion antes de abrir Chrome)
    python flujo_diario.py -y       (sin confirmacion)

Equivalentes a la cadena documentada:
    python -m src.analysis.actualizar_mes_actual yadira &&
    python -m src.analysis.informe_fichas_abiertas &&
    python -m src.tools.crear_notas_clinicas --todos --user yadira &&
    python -m src.analysis.enriquecer_informe &&
    python -m src.tools.mortadelo --todos

Importante:
- Los pasos (4) y (3) abren Chrome con login a Rayen: el operador debe
  estar presente al inicio para validar la sesion.
- El paso (4) tarda ~2-3 min (barrido del mes); el (3) scrapea una ficha
  por paciente del informe; el (7) llama al LLM por cada paciente.
- Sale en el primer paso que falle (semantica &&), con el log de error.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = ROOT / "venv" / "Scripts" / "python.exe"
if not PY.exists():  # fallback por compatibilidad si algun dia corre en Linux
    PY = ROOT / "venv" / "bin" / "python"

PASOS = [
    (
        "4/7",
        "Actualizar DB del mes (login Rayen)",
        ["-m", "src.analysis.actualizar_mes_actual", "yadira"],
    ),
    ("5/7", "Informe base de fichas abiertas", ["-m", "src.analysis.informe_fichas_abiertas"]),
    (
        "3/7",
        "Scrapear fichas del informe (login Rayen)",
        ["-m", "src.tools.crear_notas_clinicas", "--todos", "--user", "yadira"],
    ),
    ("6/7", "Enriquecer el informe", ["-m", "src.analysis.enriquecer_informe"]),
    (
        "7/7",
        "Mortadelo: fichas completas + informes de trazabilidad (LLM)",
        ["-m", "src.tools.mortadelo", "--todos"],
    ),
]


def main() -> int:
    confirmado = any(a in ("-y", "--yes") for a in sys.argv[1:])
    print(f"Flujo diario — {ROOT}")
    print(
        "Pasos: (4) actualizar DB [login Rayen] -> (5) informe base -> "
        "(3) scrapeo de fichas [login Rayen] -> (6) enriquecer -> "
        "(7) Mortadelo [LLM]"
    )
    if not confirmado:
        respuesta = (
            input("\nEsto abrira Chrome para login en Rayen. ¿Continuar? [s/N]: ").strip().lower()
        )
        if respuesta not in ("s", "si", "sí", "y", "yes"):
            print("Cancelado.")
            return 1
    for i, (num, desc, args) in enumerate(PASOS, 1):
        print(f"\n[{i}/{len(PASOS)}] (paso {num}) {desc}")
        print("-" * 60)
        resultado = subprocess.run([str(PY), *args], cwd=str(ROOT))
        if resultado.returncode != 0:
            print(
                f"\n[FALLO] El paso {num} termino con codigo {resultado.returncode}. "
                f"El flujo se detiene aqui (los pasos previos ya estan hechos)."
            )
            return resultado.returncode
    print("\n[OK] Flujo completo terminado.")
    print("Productos: informe en data/analysis/, notas en data/notas_clinicas/,")
    print("info en data/info_paciente/, anamnesis en data/anamnesis/,")
    print("fichas completas en data/fichas_generadas/, informes de")
    print("trazabilidad en data/informes_trazabilidad/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
