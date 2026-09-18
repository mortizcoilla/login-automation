"""Fechas en formato dd-mm-yyyy: el UNICO formato del proyecto.

Antes de este modulo, el literal "%d-%m-%Y" y la regex ^\\d{2}-\\d{2}-\\d{4}$
estaban duplicados en 8 archivos. Ahora viven aca.
"""

from __future__ import annotations

import re
from datetime import date, datetime

# Mismo valor que src.constants.DATE_FORMAT (re-exportado para conveniencia).
DATE_FORMAT = "%d-%m-%Y"

# Regex de fecha dd-mm-yyyy (para validar strings sin parsearlos).
FECHA_RE = re.compile(r"^\d{2}-\d{2}-\d{4}$")


def es_fecha_valida(texto: str) -> bool:
    """True si texto es una fecha dd-mm-yyyy valida (ej. '16-09-2026').

    '10-13-2026' (mes 13) es INVALIDO: no basta el patron, se parsea.
    """
    if not texto or not FECHA_RE.match(texto.strip()):
        return False
    try:
        datetime.strptime(texto.strip(), DATE_FORMAT)
    except ValueError:
        return False
    return True


def parsear_fecha(texto: str) -> date:
    """Parsea 'dd-mm-yyyy' a date. Lanza ValueError si es invalido."""
    return datetime.strptime(texto.strip(), DATE_FORMAT).date()


def fecha_hoy_str() -> str:
    """Fecha de hoy como 'dd-mm-yyyy'."""
    return date.today().strftime(DATE_FORMAT)
