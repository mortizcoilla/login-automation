# -*- coding: utf-8 -*-
"""Actualiza las docs de los bundles para reflejar el nuevo matching
del trigger `** mortadelo` (case-insensitive, tolera espacios).

Ejecutar desde la raiz del proyecto.
"""
import re
from pathlib import Path

ROOT = Path("src/mortadelo/skills")

# Bloque a anadir al inicio de la seccion "Regla X" o donde se mencione
# el trigger. Estrategia: agregar una nota dentro de "Regla 0" (la unica
# comun a todos los bundles) y un bullet en "Higiene de la ficha".

NOTA_TRIGGER = (
    "**Matching del trigger `** mortadelo` (case-insensitive, "
    "tolera espacios):** la doctora puede escribirlo como "
    "`** mortadelo`, `**Mortadelo`, `** MORTADELO`, `** Mortadelo:`, etc. "
    "Implementado en `src.mortadelo.trigger.TRIGGER_RE`. "
    "Ver `src/mortadelo/trigger.py` y `tests/test_mortadelo_trigger.py`."
)


def patch_rules_file(path: Path) -> bool:
    """Agrega la nota del trigger en la seccion 'Higiene de la ficha'
    si menciona `** mortadelo`. Retorna True si se modifico."""
    if not path.exists():
        return False
    texto = path.read_text(encoding="utf-8")
    if "src.mortadelo.trigger" in texto:
        return False  # ya actualizado
    # Patrón: lineas que contienen "** mortadelo" o "** mortadelo`"
    nuevo = re.sub(
        r"(- `\*\* mortadelo` y la instruccion interna: SE BORRA[^\n]*\n)",
        r"\1  " + NOTA_TRIGGER + "\n",
        texto,
    )
    if nuevo != texto:
        path.write_text(nuevo, encoding="utf-8")
        return True
    return False


def main() -> int:
    mods = 0
    for reglas in ROOT.glob("*/reglas.md"):
        if patch_rules_file(reglas):
            print(f"actualizado: {reglas}")
            mods += 1
    print(f"\nTotal: {mods} archivos actualizados")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
