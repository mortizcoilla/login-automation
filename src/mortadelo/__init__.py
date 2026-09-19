"""Paso 7 (Mortadelo): genera la ficha completa y el informe de trazabilidad.

Motor: CLI de opencode (decision del usuario; ver docs/REQUISITOS.md
REQ-055). El LLM propone; el CODIGO ensambla (ensamblador.py) — la ficha
final se reconstruye con garantias estructurales, no se copia tal cual
la salida del modelo.
"""

from src.mortadelo.generar import generar_fichas
from src.mortadelo.llm_cli import LLMError, llm_run

__all__ = ["LLMError", "generar_fichas", "llm_run"]
