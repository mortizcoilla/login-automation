"""Extractores por seccion de la ficha de Rayen (Fase 3c).

Cada modulo extrae una seccion de la ficha abierta. El orden de
extraccion lo orquesta crear_notas_clinicas.main (REQ-024).
"""

from src.rayen.extraccion.atencion_actual import (
    click_atencion_actual,
    extraer_anamnesis,
    extraer_motivo_consulta,
)
from src.rayen.extraccion.diagnosticos import (
    extraer_actividades,
    extraer_diagnosticos,
    extraer_profesionales,
)
from src.rayen.extraccion.estratificacion import (
    extraer_estratificacion_ecicep,
    formatear_estratificacion,
)
from src.rayen.extraccion.historial import (
    extraer_historial,
    filtrar_historial_ultimos_6_meses,
)
from src.rayen.extraccion.identificacion import extraer_identificacion
from src.rayen.extraccion.plan import (
    extraer_laboratorio,
    extraer_recetas,
)

__all__ = [
    "click_atencion_actual",
    "extraer_actividades",
    "extraer_anamnesis",
    "extraer_diagnosticos",
    "extraer_estratificacion_ecicep",
    "extraer_historial",
    "extraer_identificacion",
    "extraer_laboratorio",
    "extraer_motivo_consulta",
    "extraer_profesionales",
    "extraer_recetas",
    "filtrar_historial_ultimos_6_meses",
    "formatear_estratificacion",
]
