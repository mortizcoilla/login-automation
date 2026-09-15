"""Mapping del bundle salud_mental.

Este bundle NO duplica el mapping tipo_atencion -> plantilla. La fuente
de verdad es `PLANTILLAS.xlsx` y se consume via
`src.reglas_plantillas.resolver_plantilla`. Lo que hace este modulo es:

1. Declarar la PLANTILLA canonica del bundle (para que Mortadelo sepa
   "si resuelve a ESTE nombre, es mi bundle").
2. Exponer helpers que Mortadelo usa para responder preguntas sobre
   su propio alcance ("este tipo_atencion es mio?",
   "que tipos de atencion absorbo?").
3. Mantener el principio de no-duplicacion: si Yadira edita el Excel,
   no hay que tocar este archivo.

Regla de Yadira: una sola plantilla (`INGRESO SALUD MENTAL SIN ECICEP`)
absorbe los 4 `tipo_atencion` de salud mental (adultos e infantil).
Yadira adapta manualmente lo pediatrico al revisar.
"""
from __future__ import annotations

from typing import Final

from src.reglas_plantillas import (
    listar_tipos_con_plantilla,
    resolver_plantilla,
)

# Plantilla canonica del bundle. Vive en `plantillas/<NOMBRE>.txt`.
# Si Yadira la renombra en el Excel, esta constante hay que actualizarla
# (es la unica pieza de configuracion que el bundle mantiene propia).
PLANTILLA: Final[str] = "INGRESO SALUD MENTAL SIN ECICEP"


def es_salud_mental(tipo_atencion: str) -> bool:
    """True si el tipo_atencion pertenece a este bundle.

    Delegado al resolver canonico (que lee PLANTILLAS.xlsx). Si Yadira
    agrega o quita tipo_atencion de este bundle, no hay que tocar
    este modulo: la respuesta se actualiza sola al re-cargar el Excel.
    """
    return resolver_plantilla(tipo_atencion) == PLANTILLA


def tipos_atencion_del_bundle() -> frozenset[str]:
    """Set de tipo_atencion que este bundle absorbe (calculado en runtime).

    Equivale a "todos los tipo_atencion del Excel cuya canonica es
    `INGRESO SALUD MENTAL SIN ECICEP`". Se calcula al llamar, no al
    importar, para que refleje cualquier cambio en el Excel.
    """
    return frozenset(
        tipo for tipo, canonica in listar_tipos_con_plantilla()
        if canonica == PLANTILLA
    )


__all__ = [
    "PLANTILLA",
    "es_salud_mental",
    "tipos_atencion_del_bundle",
]
