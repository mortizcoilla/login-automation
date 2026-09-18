"""Unica fuente de verdad de paths del proyecto (absorbe informe_paths).

Regla REQ-011 (sesion 2026-09-09): los helpers de informes son la unica
forma de construir paths de informes; nunca hardcodear.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

# Raiz del repo (este archivo vive en src/core/, subimos 2 niveles).
ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = ROOT / "data"
NOTAS_DIR = DATA_DIR / "notas_clinicas"
INFO_PACIENTE_DIR = DATA_DIR / "info_paciente"
ANAMNESIS_DIR = DATA_DIR / "anamnesis"
EXAMENES_CRUDOS_DIR = DATA_DIR / "examenes_crudos"
EXAMENES_DIR = DATA_DIR / "examenes"
ADJUNTOS_DIR = DATA_DIR / "adjuntos"
ANALISIS_DIR = DATA_DIR / "analysis"
LOGS_DIR = ROOT / "logs"
SCREENSHOTS_DIR = DATA_DIR / "logs" / "screenshots"


def informe_mes_actual_path(fecha: date | None = None) -> Path:
    """Path al informe del mes en curso (mensual, NUNCA el anual).

    Ejemplos:
        informe_mes_actual_path()                  -> informe_fichas_abiertas_09-2026.txt
        informe_mes_actual_path(date(2026, 7, 15)) -> informe_fichas_abiertas_07-2026.txt
    """
    f = fecha or date.today()
    return ANALISIS_DIR / f"informe_fichas_abiertas_{f.strftime('%m-%Y')}.txt"


def informe_anual_path(anio: int | None = None) -> Path:
    """Path al informe ANUAL completo. Operacion distinta, otros objetivos.

    NO usar en flujos mensuales. Si necesitas procesar el anual, pasalo
    explicitamente con --informe.

    Ejemplos:
        informe_anual_path()     -> informe_fichas_abiertas_2026_completo.txt
        informe_anual_path(2025) -> informe_fichas_abiertas_2025_completo.txt
    """
    a = anio or date.today().year
    return ANALISIS_DIR / f"informe_fichas_abiertas_{a}_completo.txt"
