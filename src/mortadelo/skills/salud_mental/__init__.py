"""Skill bundle: salud_mental.

Mapea todos los `tipo_atencion` de salud mental a la plantilla canonica
`INGRESO SALUD MENTAL SIN ECICEP`. La fuente de verdad del mapping es
`PLANTILLAS.xlsx` (ver `src.reglas_plantillas`); este bundle NO duplica
el mapping, solo lo consume.
"""

from src.mortadelo.skills.salud_mental.mapping import (
    PLANTILLA,
    es_salud_mental,
    tipos_atencion_del_bundle,
)
from src.reglas_plantillas import resolver_plantilla

__all__ = [
    "PLANTILLA",
    "es_salud_mental",
    "resolver_plantilla",
    "tipos_atencion_del_bundle",
]
