"""Mapping del bundle ecicep (consolidado: ingreso + control).

Los manuales ECICEP aplican a TODO el flujo (ingreso y control). Por eso
es un solo bundle con dos sub-flujos segun el `tipo_atencion`:

  Ingreso: tipo_atencion empieza con "Ingreso" + ecicep/multimorbilidad
    -> plantilla: INGRESO ECICEP

  Control: tipo_atencion empieza con "Control" + ecicep/cronico
    -> plantilla: CONTROL INTEGRAL SIN FICHA ANTERIOR

Este bundle NO duplica el mapping tipo_atencion -> plantilla. La fuente
de verdad es `_REGLA` en `src.reglas_plantillas`, que se consume via
`resolver_plantilla`. Lo que hace este modulo es:

1. Declarar las PLANTILLAS canonicas del bundle.
2. Exponer helpers que Mortadelo usa para responder preguntas sobre
   su propio alcance.
"""
from __future__ import annotations

from typing import Final

from src.reglas_plantillas import (
    listar_tipos_con_plantilla,
    resolver_plantilla,
)

# Plantillas canonicas que este bundle absorbe.
# - Ingreso ECICEP: g1/g2/g3, multimorbilidad g2/g3
# - Control integral sin ficha anterior: ecicep-*, control cronico
PLANTILLA_INGRESO: Final[str] = "INGRESO ECICEP"
PLANTILLA_CONTROL: Final[str] = "CONTROL INTEGRAL SIN FICHA ANTERIOR"
PLANTILLAS_ECICEP: Final[frozenset[str]] = frozenset({
    PLANTILLA_INGRESO,
    PLANTILLA_CONTROL,
})


def es_ecicep(tipo_atencion: str) -> bool:
    """True si el tipo_atencion es de cualquier atencion ECICEP."""
    return resolver_plantilla(tipo_atencion) in PLANTILLAS_ECICEP


def es_ecicep_ingreso(tipo_atencion: str) -> bool:
    """True si es ECICEP ingreso (assessment inicial)."""
    return resolver_plantilla(tipo_atencion) == PLANTILLA_INGRESO


def es_ecicep_control(tipo_atencion: str) -> bool:
    """True si es ECICEP control (seguimiento)."""
    return resolver_plantilla(tipo_atencion) == PLANTILLA_CONTROL


def plantilla_para(tipo_atencion: str) -> str | None:
    """Devuelve la plantilla canonica para el tipo_atencion, o None
    si no es de ECICEP."""
    canonica = resolver_plantilla(tipo_atencion)
    if canonica in PLANTILLAS_ECICEP:
        return canonica
    return None


def tipos_atencion_del_bundle() -> frozenset[str]:
    """Set de tipo_atencion que este bundle absorbe (calculado en runtime)."""
    return frozenset(
        tipo for tipo, canonica in listar_tipos_con_plantilla()
        if canonica in PLANTILLAS_ECICEP
    )


__all__ = [
    "PLANTILLA_INGRESO",
    "PLANTILLA_CONTROL",
    "PLANTILLAS_ECICEP",
    "es_ecicep",
    "es_ecicep_ingreso",
    "es_ecicep_control",
    "plantilla_para",
    "tipos_atencion_del_bundle",
]
