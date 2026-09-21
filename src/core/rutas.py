"""Unica fuente de verdad de paths del proyecto (absorbe informe_paths).

Regla REQ-011 (sesion 2026-09-09): los helpers de informes son la unica
forma de construir paths de informes; nunca hardcodear.

REQ-059: cada directorio de productos es configurable desde .env (bloque
"Rutas de productos" en .env.example). Defaults relativos a la raiz del
repo, para que clonar en otro PC no requiera editar nada;DATA_DIR mueve
todos los productos de una sola vez.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

# Patron de src/credentials.py: el modulo que lee env del .env lo carga.
# rutas se importa al inicio de casi todo el proyecto, por lo que ademas
# deja el .env disponible para el resto de los modulos.
load_dotenv()

# Raiz del repo (este archivo vive en src/core/, subimos 2 niveles).
ROOT = Path(__file__).resolve().parents[2]


def _dir_desde_env(variable: str, default: Path) -> Path:
    """Lee un directorio desde env; ausente o vacio -> default.

    Rutas relativas se resuelven contra la raiz del repo (no contra el
    CWD), para que "notas_clinicas" signifique lo mismo sin importar
    desde donde se ejecute el comando.
    """
    valor = os.getenv(variable, "").strip()
    if not valor:
        return default
    ruta = Path(valor).expanduser()
    return ruta if ruta.is_absolute() else ROOT / ruta


# Los derivados heredan el override de DATA_DIR: basta mover DATA_DIR
# para reubicar todos los productos, y un override individual para uno.
DATA_DIR = _dir_desde_env("DATA_DIR", ROOT / "data")
NOTAS_DIR = _dir_desde_env("NOTAS_CLINICAS_DIR", DATA_DIR / "notas_clinicas")
INFO_PACIENTE_DIR = _dir_desde_env("INFO_PACIENTE_DIR", DATA_DIR / "info_paciente")
ANAMNESIS_DIR = _dir_desde_env("ANAMNESIS_DIR", DATA_DIR / "anamnesis")
EXAMENES_CRUDOS_DIR = _dir_desde_env("EXAMENES_CRUDOS_DIR", DATA_DIR / "examenes_crudos")
EXAMENES_DIR = _dir_desde_env("EXAMENES_DIR", DATA_DIR / "examenes")
ADJUNTOS_DIR = _dir_desde_env("ADJUNTOS_DIR", DATA_DIR / "adjuntos")
FICHAS_GENERADAS_DIR = _dir_desde_env("FICHAS_GENERADAS_DIR", DATA_DIR / "fichas_generadas")
INFORMES_TRAZABILIDAD_DIR = _dir_desde_env(
    "INFORMES_TRAZABILIDAD_DIR", DATA_DIR / "informes_trazabilidad"
)
ANALISIS_DIR = _dir_desde_env("ANALYSIS_DIR", DATA_DIR / "analysis")
SCREENSHOTS_DIR = _dir_desde_env("SCREENSHOTS_DIR", DATA_DIR / "logs" / "screenshots")
LOGS_DIR = _dir_desde_env("LOGS_DIR", ROOT / "logs")


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
