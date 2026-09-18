"""Sanitizacion del tipo de atencion (REQ-037).

Rayen antepone prefijos de instrumento (ME, EN, PS, TO, NU, KT) al nombre
canonico del tipo de atencion. Esta funcion los remueve.

Historia: vivia en src.plantillas (eliminado); la limpieza de 2026-09-18
dejo DOS copias inlined (actualizar_mes_actual y listar_iniciados). Este
modulo es la unica copia desde la refactorizacion 2026-09-18.
"""

from __future__ import annotations

import re

from src.constants import INSTRUMENTO_PREFIXES

_INSTRUMENTO_PREFIX_RE = re.compile(
    r"^(?:" + "|".join(re.escape(p) for p in INSTRUMENTO_PREFIXES) + r")\s*",
    re.IGNORECASE,
)


def sanitizar_tipo(tipo_atencion: str) -> str:
    """Remueve prefijos de instrumento del tipo de atencion.

    Ej. 'ME, Control de nino sano' -> 'Control de nino sano'.
    String vacio retorna vacio.
    """
    if not tipo_atencion:
        return ""
    return _INSTRUMENTO_PREFIX_RE.sub("", tipo_atencion.strip()).strip()
