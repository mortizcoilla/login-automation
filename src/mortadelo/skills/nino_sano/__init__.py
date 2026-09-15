"""Skill bundle: nino_sano (Control de Nino Sano 0-9 anos en APS).

Se dispara cuando `tipo_atencion == "Control salud"`. La plantilla
concreta (1 MES o 3 MESES) se decide por EDAD segun
`resolver_plantilla(tipo, edad_meses)`.

La fuente de verdad del mapping es `_REGLA` en `src.reglas_plantillas`.
Este bundle NO la duplica.

No improvisa. Si el caso esta fuera de la cobertura del bundle
(manuales validados), lo reporta en `** Doctora:` y deriva a la doctora.
"""

from src.mortadelo.skills.nino_sano.mapping import (
    LIMITE_MESES_NINO_SANO,
    PLANTILLA_1MES,
    PLANTILLA_3MESES,
    PLANTILLAS_NINO_SANO,
    es_nino_sano,
    es_tipo_control_salud,
    plantilla_para,
    requiere_edad,
    tipos_atencion_del_bundle,
)
from src.reglas_plantillas import resolver_plantilla

__all__ = [
    "LIMITE_MESES_NINO_SANO",
    "PLANTILLA_1MES",
    "PLANTILLA_3MESES",
    "PLANTILLAS_NINO_SANO",
    "es_nino_sano",
    "es_tipo_control_salud",
    "plantilla_para",
    "requiere_edad",
    "resolver_plantilla",
    "tipos_atencion_del_bundle",
]
