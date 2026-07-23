"""Skill: leer el contenido detallado de una ficha específica.

Abre la ficha indicada y extrae:
- Las notas clínicas que escribió la médica
- El estado actual de la ficha
- Los metadatos del paciente

Por ahora, como la UI de Rayen no permite acceso programático fácil a las
notas clínicas (requiere navegar a otra vista), esta skill devuelve los
datos que ya están en la tabla de Pacientes citados. En el futuro, cuando
descubramos el endpoint o flujo exacto para abrir una ficha, esta skill
se ampliará para incluir el contenido del editor de notas.

El TODO al final del archivo es explícito sobre esto.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.pancho_skills.listar_iniciados import PacienteIniciado


@dataclass
class FichaDetalle:
    """Detalle de una ficha específica.

    Por ahora es lo mismo que PacienteIniciado (los datos que ya están
    en la tabla). En el futuro incluirá el contenido de las notas clínicas.
    """

    paciente: PacienteIniciado
    notas_clinicas: str  # vacío por ahora — ver TODO
    metadata_extra: dict[str, str]  # placeholder para campos adicionales


def leer_ficha(
    paciente: PacienteIniciado,
    logger: logging.Logger,
) -> FichaDetalle:
    """Lee el detalle de una ficha específica.

    Args:
        paciente: el PacienteIniciado seleccionado de la lista.
        logger: logger compartido.

    Returns:
        FichaDetalle con los datos disponibles.

    TODO: cuando se descubra el flujo UI/API para abrir una ficha
    específica y extraer las notas clínicas, esta función debe:
    1. Hacer clic en la fila del paciente
    2. Esperar a que cargue la vista de detalle
    3. Extraer el contenido del campo de notas
    4. Navegar de vuelta a la lista
    Por ahora solo devuelve los datos que ya teníamos.
    """
    logger.info(
        f"[pancho] Leyendo detalle de ficha para '{paciente.nombre}' "
        f"(tipo: {paciente.tipo_atencion})"
    )
    return FichaDetalle(
        paciente=paciente,
        notas_clinicas="",  # TODO: extraer de la UI
        metadata_extra={},
    )
