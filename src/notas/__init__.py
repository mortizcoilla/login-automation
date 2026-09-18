"""Capa notas: escritura de los documentos para Yadira (Fase 4a).

- modelos: PacienteObjetivo.
- nota_clinica: la nota .md completa + validacion.
- info_paciente: vista rapida sin anamnesis.
- anamnesis: respaldo crudo de la anamnesis + motivo.
"""

from src.notas.anamnesis import guardar_respaldo_anamnesis
from src.notas.info_paciente import guardar_info_paciente
from src.notas.modelos import PacienteObjetivo
from src.notas.nota_clinica import (
    _rellenar_bloque_en_nota,
    _safe_filename,
    guardar_nota_clinica,
    validar_nota_clinica,
)

__all__ = [
    "PacienteObjetivo",
    "_rellenar_bloque_en_nota",
    "_safe_filename",
    "guardar_info_paciente",
    "guardar_nota_clinica",
    "guardar_respaldo_anamnesis",
    "validar_nota_clinica",
]
