"""Skill bundle: examenes (lectura de examenes adjuntos).

Stubs. En produccion: OCR para imagenes, pdfplumber/PyMuPDF para
PDFs, vision LLM para interpretacion clinica.

Hoy: `leer_examen()` retorna dict vacio. Yadira procesa los examenes
manualmente o los transcribe a la nota de texto.
"""
from src.mortadelo.skills.examenes.mapping import (
    detectar_tipo_examen,
    interpretar_audiometria,
    leer_examen,
)

__all__ = [
    "detectar_tipo_examen",
    "interpretar_audiometria",
    "leer_examen",
]
