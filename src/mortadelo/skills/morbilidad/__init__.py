"""Skill bundle: morbilidad.

Mapea los `tipo_atencion` de morbilidad (4 variantes segun
`reglas_plantillas._REGLA`) a la plantilla canonica `MORBILIDAD`.
La fuente de verdad del mapping es el dict en codigo; este bundle
NO la duplica.

No improvisa. Si el caso esta fuera de la cobertura del bundle
(manuales validados), lo reporta en `** Doctora:` y deriva a la doctora.
"""

from src.mortadelo.skills.morbilidad.mapping import (
    PLANTILLA,
    es_morbilidad,
    tipos_atencion_del_bundle,
)
from src.reglas_plantillas import resolver_plantilla

__all__ = [
    "PLANTILLA",
    "es_morbilidad",
    "resolver_plantilla",
    "tipos_atencion_del_bundle",
]
