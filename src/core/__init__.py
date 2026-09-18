"""Kernel compartido del proyecto: utilidades puras sin Selenium ni I/O de Rayen.

Modulos:
- fechas: parseo/validacion dd-mm-yyyy (formato unico del proyecto).
- nombres: normalizacion y convenciones de filename (dos: crudos y notas).
- tipos_atencion: sanitizado de prefijos de instrumento de Rayen.
- rutas: ROOT y unica fuente de verdad de paths de data/ e informes.

REQ asociados: REQ-008 (cadena diaria), REQ-011 (aislamiento mensual/anual),
REQ-037 (sanitizacion de tipos), REQ-039 (paths de informes).
"""

from src.core.fechas import DATE_FORMAT, FECHA_RE, es_fecha_valida, parsear_fecha
from src.core.nombres import nombre_a_filename, normalizar_texto, safe_filename
from src.core.rutas import (
    ADJUNTOS_DIR,
    ANALISIS_DIR,
    ANAMNESIS_DIR,
    DATA_DIR,
    EXAMENES_CRUDOS_DIR,
    EXAMENES_DIR,
    INFO_PACIENTE_DIR,
    NOTAS_DIR,
    ROOT,
    informe_anual_path,
    informe_mes_actual_path,
)
from src.core.tipos_atencion import sanitizar_tipo

__all__ = [
    "ADJUNTOS_DIR",
    "ANALISIS_DIR",
    "ANAMNESIS_DIR",
    "DATA_DIR",
    "DATE_FORMAT",
    "EXAMENES_CRUDOS_DIR",
    "EXAMENES_DIR",
    "FECHA_RE",
    "INFO_PACIENTE_DIR",
    "NOTAS_DIR",
    "ROOT",
    "es_fecha_valida",
    "informe_anual_path",
    "informe_mes_actual_path",
    "nombre_a_filename",
    "normalizar_texto",
    "parsear_fecha",
    "safe_filename",
    "sanitizar_tipo",
]
