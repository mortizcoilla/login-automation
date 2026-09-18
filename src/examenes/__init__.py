"""Paso 2: examenes (opt-in por paciente, REQ-009/047).

- archivar: (paso 2a) vive en src/tools/recibir_foto_examen.py.
- vision_api: cliente z.ai GLM vision.
- consolidar: (paso 2b) fotos crudas -> exam_<pac>_<fecha>.md.
"""

from src.examenes.consolidar import buscar_fotos_crudas, consolidar_examenes
from src.examenes.vision_api import VisionAPIError, transcribir_imagen

__all__ = [
    "VisionAPIError",
    "buscar_fotos_crudas",
    "consolidar_examenes",
    "transcribir_imagen",
]
