"""Regla de uso de plantillas: que plantilla usar para cada tipo de atencion.

La fuente de verdad es el dict `_REGLA` definido en este modulo. Cualquier
modificacion (agregar/quitar/renombrar) se hace editando este archivo y
reiniciando el proceso.

Para mantener el mapping actualizado, editar `_REGLA` directamente. NO
se lee ningun archivo externo en runtime.

Matching: case-insensitive y accent-insensitive. La clave "Morbilidad
telefónica" (con acento) y "MORBILIDAD TELEFONICA" (mayusculas, sin
acento) matchean. Esto resuelve diferencias entre lo que manda Rayen
y lo que esta escrito aca.

Caso especial: el valor `CONTROL DE NIÑO SANO` es un placeholder. El
resolver, en lugar de devolver ese string, usa `edad_meses` para elegir
entre `CONTROL NIÑO SANO 1 MES` (bebes < 3 meses) y `CONTROL NIÑO SANO
3 MESES` (bebes >= 3 meses). Sin edad, devuelve None.
"""
from __future__ import annotations

import unicodedata
from typing import Final

from src.plantillas import sanitizar_tipo

# Sentinel: este tipo NO usa plantilla del sistema.
_NO_APLICA: Final[str] = "NO APLICA"

# Placeholder para "Control de nino sano". El resolver lo expande segun
# la edad del paciente.
_PLACEHOLDER_NINO_SANO: Final[str] = "CONTROL DE NIÑO SANO"

# Limite en meses para elegir 1 mes vs 3 meses en Control de Nino Sano.
LIMITE_MESES_NINO_SANO: Final[int] = 3


# --- Fuente de verdad: tipo_atencion (Rayen) -> plantilla canonica ---
# Editar este dict para modificar el mapping. Las claves pueden tener
# acentos, mayusculas/minusculas, espacios; el matching es robusto.
_REGLA: dict[str, str] = {
    # Recetas
    "Recetas": "RECETA",
    # Morbilidad (cualquier variante)
    "Morbilidad telefónica": "MORBILIDAD",
    "Morbilidad presencial": "MORBILIDAD",
    "Control cronico descompensado": "MORBILIDAD",
    "Morbilidad": "MORBILIDAD",
    # Ingreso salud mental (sin ECICEP)
    "Ingreso salud mental infantil": "INGRESO SALUD MENTAL SIN ECICEP",
    "Ingreso multidisciplinario salud mental - infantil": "INGRESO SALUD MENTAL SIN ECICEP",
    "Control salud mental infantil": "INGRESO SALUD MENTAL SIN ECICEP",
    "Consulta salud mental": "INGRESO SALUD MENTAL SIN ECICEP",
    # Ingreso ECICEP
    "Ingreso integral ecicep-g3": "INGRESO ECICEP",
    "Ingreso multimorbilidad g3": "INGRESO ECICEP",
    "Ingreso multimorbilidad g2": "INGRESO ECICEP",
    "Ingreso integral ecicep-g2": "INGRESO ECICEP",
    "Ingreso integral ecicep-g1": "INGRESO ECICEP",
    # Control integral sin ficha anterior (cualquier variante)
    "Control integral ecicep-g3": "CONTROL INTEGRAL SIN FICHA ANTERIOR",
    "Control integral multimorbilidad g3": "CONTROL INTEGRAL SIN FICHA ANTERIOR",
    "Control integral ecicep-g2": "CONTROL INTEGRAL SIN FICHA ANTERIOR",
    "Control integral multimorbilidad g2": "CONTROL INTEGRAL SIN FICHA ANTERIOR",
    "Control integral multimorbilidad g1": "CONTROL INTEGRAL SIN FICHA ANTERIOR",
    "Control integral ecicep-g1": "CONTROL INTEGRAL SIN FICHA ANTERIOR",
    "Control crónico": "CONTROL INTEGRAL SIN FICHA ANTERIOR",
    # Control de nino sano (placeholder, se calcula con edad)
    "Control salud": _PLACEHOLDER_NINO_SANO,
    # NO APLICA: tipos que no usan plantilla del sistema
    "Gestion administrativa": _NO_APLICA,
    "Seguimiento a distancia multimorbilidad g2": _NO_APLICA,
    "Consultorías adulto": _NO_APLICA,
    "Consultoria salud mental (sesiones)": _NO_APLICA,
    "Control": _NO_APLICA,
}


def _normalizar_clave(s: str) -> str:
    """Normaliza para matching: lowercase + sin acentos + colapsar espacios."""
    if not s:
        return ""
    # NFKD descompone acentos en letra + combining mark; descartamos los marks.
    nfkd = unicodedata.normalize("NFKD", s)
    sin_acentos = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(sin_acentos.lower().split())


def _resolver_control_nino_sano(edad_meses: int | None) -> str | None:
    """Elige entre CONTROL NIÑO SANO 1 MES y 3 MESES según la edad.

    Returns None si no se puede determinar (falta edad).
    """
    if edad_meses is None:
        return None
    if edad_meses < LIMITE_MESES_NINO_SANO:
        return "CONTROL NIÑO SANO 1 MES"
    return "CONTROL NIÑO SANO 3 MESES"


def resolver_plantilla(
    tipo_atencion: str, edad_meses: int | None = None
) -> str | None:
    """Dado un tipo de atencion de Rayen, devuelve el nombre canonico
    de la plantilla a usar, o None si no aplica.

    Caso especial: si la regla dice 'CONTROL DE NIÑO SANO' (placeholder),
    usa `edad_meses` para elegir entre 1 mes y 3 meses. Sin edad, devuelve
    None (no se puede resolver).

    Args:
        tipo_atencion: tipo que viene de Rayen (ej. "Morbilidad telefonica").
        edad_meses: edad del paciente en meses. Necesario SOLO para
            "Control de nino sano" (donde hay 2 plantillas segun edad).
            Si no se pasa, devuelve None para ese caso.

    Returns:
        - None si el tipo no esta en la regla
        - None si la regla dice 'NO APLICA' para ese tipo
        - El nombre canonico de la plantilla (uppercase) en caso contrario
    """
    if not tipo_atencion:
        return None
    tipo = _normalizar_clave(sanitizar_tipo(tipo_atencion))
    if not tipo:
        return None
    for clave, canonica in _REGLA.items():
        if _normalizar_clave(clave) == tipo:
            if canonica == _NO_APLICA:
                return None
            if canonica == _PLACEHOLDER_NINO_SANO:
                return _resolver_control_nino_sano(edad_meses)
            return canonica
    return None


def listar_tipos_con_plantilla() -> list[tuple[str, str]]:
    """Devuelve la lista de (tipo_atencion, plantilla) para los tipos
    que SÍ tienen plantilla asignada (omite 'NO APLICA' y vacios).
    """
    return [
        (tipo, canonica)
        for tipo, canonica in _REGLA.items()
        if canonica != _NO_APLICA and tipo != ""
    ]


def listar_plantillas_canonicas() -> list[str]:
    """Devuelve la lista unica de plantillas canonicas (uppercase)."""
    return sorted({c for c in _REGLA.values() if c != _NO_APLICA})
