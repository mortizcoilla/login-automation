"""Capa informes: pasos 4-6 del flujo diario (Fase 4b).

- parser: parser UNICO del informe (REQ-043/053).
- mes: paso 4 (actualizar DB del mes).
- base: paso 5 (informe basico 5 columnas).
- enriquecer: paso 6 (informe enriquecido 8 columnas).
"""

from src.informes.parser import (
    parsear_filas_enriquecidas,
    parsear_linea_informe,
    parsear_pacientes_objetivo,
)

__all__ = [
    "parsear_filas_enriquecidas",
    "parsear_linea_informe",
    "parsear_pacientes_objetivo",
]
