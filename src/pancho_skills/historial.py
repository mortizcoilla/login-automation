"""Skill: historial clínico y farmacéutico del paciente.

STUB — esta skill requiere descubrir los endpoints de Rayen para los
módulos de Historia Clínica y Recetas/Fármacos. Hasta que eso pase,
esta función solo existe como placeholder tipado.

Plan de implementación:
1. Usar `discover_api.py` con sesión activa para navegar a Historia
   clínica de un paciente y capturar el endpoint.
2. Repetir para el módulo de Recetas/Fármacos.
3. Implementar la skill usando `api_client` (que ya está en el proyecto).
4. Si los endpoints requieren autenticación adicional, manejar el refresh
   de la sesión desde aquí.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any


@dataclass
class HistorialClinico:
    """Historial clínico del paciente (de Rayen)."""

    paciente_id: str
    consultas_previas: list[dict[str, Any]] = field(default_factory=list)
    diagnosticos_previos: list[str] = field(default_factory=list)
    examenes_previos: list[dict[str, Any]] = field(default_factory=list)
    antecedentes: dict[str, str] = field(default_factory=dict)


@dataclass
class HistorialFarmaco:
    """Historial farmacéutico del paciente (de Rayen)."""

    paciente_id: str
    medicamentos_activos: list[dict[str, str]] = field(default_factory=list)
    alergias: list[str] = field(default_factory=list)
    recetas_historicas: list[dict[str, str]] = field(default_factory=list)


@dataclass
class HistorialCompleto:
    """Historial clínico + farmacéutico del paciente."""

    clinico: HistorialClinico
    farmaco: HistorialFarmaco


def obtener_historial(
    paciente_id: str,
    logger: logging.Logger,
) -> HistorialCompleto:
    """STUB — devuelve un historial vacío.

    Raises:
        NotImplementedError: hasta que se descubran los endpoints de Rayen.
    """
    logger.warning(
        f"[pancho] obtener_historial('{paciente_id}') es un STUB. "
        "Falta descubrir los endpoints de Rayen."
    )
    raise NotImplementedError(
        "obtener_historial no está implementado. "
        "Pasos: (1) correr src/discover_api.py con sesión activa, "
        "(2) navegar a Historia clínica y Recetas de un paciente, "
        "(3) capturar los endpoints, (4) implementar esta función."
    )
