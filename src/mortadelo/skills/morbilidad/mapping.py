"""Mapping del bundle morbilidad.

Este bundle NO duplica el mapping tipo_atencion -> plantilla. La fuente
de verdad es `_REGLA` en `src.reglas_plantillas`, que se consume via
`resolver_plantilla`. Lo que hace este modulo es:

1. Declarar la PLANTILLA canonica del bundle.
2. Exponer helpers que Mortadelo usa para responder preguntas sobre
   su propio alcance ("este tipo_atencion es mio?",
   "que tipos de atencion absorbo?").

Regla de Yadira: una sola plantilla (`MORBILIDAD`) absorbe las 4
variantes de morbilidad (presencial, telefonica, control cronico
descompensado, y morbilidad a secas). Yadira adapta manualmente el
formato al revisar.
"""
from __future__ import annotations

from typing import Final

from src.reglas_plantillas import (
    listar_tipos_con_plantilla,
    resolver_plantilla,
)

# Plantilla canonica del bundle. Vive en `plantillas/<NOMBRE>.txt`.
# Si Yadira la renombra en `_REGLA`, esta constante hay que actualizarla.
PLANTILLA: Final[str] = "MORBILIDAD"


def es_morbilidad(tipo_atencion: str) -> bool:
    """True si el tipo_atencion pertenece a este bundle.

    Delegado al resolver canonico (que lee `_REGLA`). Si Yadira
    agrega o quita tipo_atencion de este bundle, no hay que tocar
    este modulo: la respuesta se actualiza sola al re-cargar el dict.
    """
    return resolver_plantilla(tipo_atencion) == PLANTILLA


def tipos_atencion_del_bundle() -> frozenset[str]:
    """Set de tipo_atencion que este bundle absorbe (calculado en runtime).

    Equivale a "todos los tipo_atencion de `_REGLA` cuya canonica es
    `MORBILIDAD`". Se calcula al llamar, no al importar, para que
    refleje cualquier cambio en el dict.
    """
    return frozenset(
        tipo for tipo, canonica in listar_tipos_con_plantilla()
        if canonica == PLANTILLA
    )


__all__ = [
    "PLANTILLA",
    "es_morbilidad",
    "tipos_atencion_del_bundle",
]
