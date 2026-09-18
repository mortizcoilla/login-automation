"""Path helpers para los informes de fichas abiertas.

Regla del proyecto (sesion 2026-09-09):
- Cuando se trabaja con el mes en curso, el informe debe apuntar al
  mes en curso automaticamente (default).
- El informe ANUAL (`_completo.txt`) es una operacion distinta, para
  otros propositos, y se pide explicitamente. NO se mezcla con el
  flujo mensual.

Estos helpers son la unica fuente de verdad para construir paths de
informes. Cualquier codigo que necesite apuntar a un informe mensual
o anual DEBE usar estas funciones (no hardcodear paths).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "analysis"


def informe_mes_actual_path(fecha: date | None = None) -> Path:
    """Path al informe del mes en curso (mensual, NUNCA el anual).

    Ejemplos:
        informe_mes_actual_path()                          -> informe_fichas_abiertas_09-2026.txt
        informe_mes_actual_path(date(2026, 7, 15))         -> informe_fichas_abiertas_07-2026.txt
    """
    f = fecha or date.today()
    return DATA_DIR / f"informe_fichas_abiertas_{f.strftime('%m-%Y')}.txt"


def informe_anual_path(anio: int | None = None) -> Path:
    """Path al informe ANUAL completo. Operacion distinta, otros objetivos.

    NO usar en flujos mensuales. Si necesitas procesar el anual,
    pasalo explicitamente con --informe.

    Ejemplos:
        informe_anual_path()              -> informe_fichas_abiertas_2026_completo.txt
        informe_anual_path(2025)          -> informe_fichas_abiertas_2025_completo.txt
    """
    a = anio or date.today().year
    return DATA_DIR / f"informe_fichas_abiertas_{a}_completo.txt"
