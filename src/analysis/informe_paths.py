"""Shim de compatibilidad: los paths de informes viven en src.core.rutas.

Historico: este modulo fue la fuente unica (sesion 2026-09-09). Desde la
refactorizacion 2026-09-18 la implementacion vive en `src/core/rutas.py`
y este archivo solo re-exporta, para no romper los imports existentes.

REQ-011: aislamiento mensual/anual. Ver docs/REQUISITOS.md.
"""

from __future__ import annotations

from src.core.rutas import informe_anual_path, informe_mes_actual_path

__all__ = ["informe_anual_path", "informe_mes_actual_path"]
