"""Skill bundle: ecicep.

Mapea TODOS los `tipo_atencion` de ECICEP (ingreso + control, 12 variantes
segun `reglas_plantillas._REGLA`) a sus plantillas canonicas. Los manuales
validados son los mismos para ingreso y control (el marco ECICEP es uno).

La fuente de verdad del mapping es el dict en codigo; este bundle
NO la duplica.
"""

from src.mortadelo.skills.ecicep.mapping import (
    PLANTILLAS_ECICEP,
    es_ecicep,
    es_ecicep_ingreso,
    es_ecicep_control,
    plantilla_para,
    tipos_atencion_del_bundle,
)
from src.reglas_plantillas import resolver_plantilla

__all__ = [
    "PLANTILLAS_ECICEP",
    "es_ecicep",
    "es_ecicep_ingreso",
    "es_ecicep_control",
    "plantilla_para",
    "resolver_plantilla",
    "tipos_atencion_del_bundle",
]
