"""Regla de uso de plantillas: que plantilla usar para cada tipo de atencion.

La fuente de verdad es el Excel 'PLANTILLAS.xlsx' que mantiene Yadira.
Aca esta la representacion en codigo para que el sistema pueda
resolver automaticamente que plantilla cargar dado un tipo de
atencion de Rayen.

Tipos de atencion (en Rayen) -> Plantilla canonica (en plantillas/).
Si el tipo no aparece en la regla, NO hay plantilla canonica
asignada y resolver_plantilla() devuelve None.

Plantillas con valor 'NO APLICA' indican que ese tipo NO usa
plantilla del sistema (ej. gestion administrativa, consultorias).
"""
from __future__ import annotations

from src.plantillas import sanitizar_tipo

# Regla extraida de PLANTILLAS.xlsx (Hoja1, columna B = Plantilla).
# Claves en lowercase para matching case-insensitive.
# Valores: nombre canonico de la plantilla (uppercase) o 'NO APLICA'.
_REGLA: dict[str, str] = {
    # Recetas
    "recetas": "RECETA",
    # Morbilidad (cualquier variante)
    "morbilidad telefónica": "MORBILIDAD",
    "morbilidad presencial": "MORBILIDAD",
    "control cronico descompensado": "MORBILIDAD",
    "morbilidad": "MORBILIDAD",
    # Ingreso salud mental (sin ECICEP)
    "ingreso salud mental infantil": "INGRESO SALUD MENTAL SIN ECICEP",
    "ingreso multidisciplinario salud mental - infantil": "INGRESO SALUD MENTAL SIN ECICEP",
    "control salud mental infantil": "INGRESO SALUD MENTAL SIN ECICEP",
    "consulta salud mental": "INGRESO SALUD MENTAL SIN ECICEP",
    # Ingreso ECICEP
    "ingreso integral ecicep-g3": "INGRESO ECICEP",
    "ingreso multimorbilidad g3": "INGRESO ECICEP",
    "ingreso multimorbilidad g2": "INGRESO ECICEP",
    "ingreso integral ecicep-g2": "INGRESO ECICEP",
    "ingreso integral ecicep-g1": "INGRESO ECICEP",
    # Control integral sin ficha anterior (cualquier variante)
    "control integral ecicep-g3": "CONTROL INTEGRAL SIN FICHA ANTERIOR",
    "control integral multimorbilidad g3": "CONTROL INTEGRAL SIN FICHA ANTERIOR",
    "control integral ecicep-g2": "CONTROL INTEGRAL SIN FICHA ANTERIOR",
    "control integral multimorbilidad g2": "CONTROL INTEGRAL SIN FICHA ANTERIOR",
    "control integral multimorbilidad g1": "CONTROL INTEGRAL SIN FICHA ANTERIOR",
    "control integral ecicep-g1": "CONTROL INTEGRAL SIN FICHA ANTERIOR",
    "control crónico": "CONTROL INTEGRAL SIN FICHA ANTERIOR",
    # Control de nino sano
    "control salud": "CONTROL DE NIÑO SANO",
    # NO APLICA
    "": "NO APLICA",
    "gestion administrativa": "NO APLICA",
    "seguimiento a distancia multimorbilidad g2": "NO APLICA",
    "consultorías adulto": "NO APLICA",
    "consultoria salud mental (sesiones)": "NO APLICA",
    "control": "NO APLICA",
}


def resolver_plantilla(tipo_atencion: str) -> str | None:
    """Dado un tipo de atencion de Rayen, devuelve el nombre canonico
    de la plantilla a usar, o None si no aplica.

    La busqueda es case-insensitive y aplica sanitizar_tipo (quita
    prefijos de instrumento tipo 'ME,') antes de matchear.

    Returns:
        - None si el tipo no esta en la regla
        - None si la regla dice 'NO APLICA' para ese tipo
        - El nombre canonico de la plantilla (uppercase) en caso contrario
    """
    if not tipo_atencion:
        return None
    tipo = sanitizar_tipo(tipo_atencion).lower().strip()
    if not tipo:
        return None
    canonica = _REGLA.get(tipo)
    if canonica is None or canonica == "NO APLICA":
        return None
    return canonica


def listar_tipos_con_plantilla() -> list[tuple[str, str]]:
    """Devuelve la lista de (tipo_atencion, plantilla) para los tipos
    que SÍ tienen plantilla asignada (omite 'NO APLICA').
    """
    return [
        (tipo, canonica)
        for tipo, canonica in _REGLA.items()
        if canonica != "NO APLICA"
    ]


def listar_plantillas_canonicas() -> list[str]:
    """Devuelve la lista unica de plantillas canonicas (uppercase)."""
    return sorted({c for c in _REGLA.values() if c != "NO APLICA"})
