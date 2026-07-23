"""Skill: listar fichas en estado "Iniciado" para una fecha.

Navega a la página de Pacientes citados, selecciona la fecha indicada,
ordena por estado, y devuelve las fichas que están en "Iniciado" como
lista de dataclasses `PacienteIniciado`.

NO filtra por tipo de atención ni por hora — eso lo decide Pilita después.
Solo trae los datos crudos de la tabla.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from selenium.webdriver.remote.webdriver import WebDriver

from src.browser_automation import (
    ensure_session_alive,
    extraer_datos_fila,
    get_pacientes_iniciados,
    select_date,
    sort_by_estado,
)
from src.plantillas import sanitizar_tipo


@dataclass
class PacienteIniciado:
    """Datos básicos de una ficha en estado 'Iniciado'.

    Solo lo que la tabla de Rayen muestra en sus 9 columnas. Para
    información más detallada (notas clínicas, historia), usar la
    skill `leer_ficha` o `obtener_historial`.
    """

    hora: str
    estado: str
    nombre: str
    tipo_cupo: str
    llegada: str
    llamada: str
    razon: str
    tipo_atencion_raw: str  # incluye prefijo "ME," si lo trae
    tipo_atencion: str  # limpio, sin prefijo de instrumento
    adjunto: str


def listar_iniciados(
    driver: WebDriver,
    logger: logging.Logger,
    fecha: str | None = None,
) -> list[PacienteIniciado]:
    """Devuelve las fichas en estado "Iniciado" para la fecha indicada.

    Args:
        driver: WebDriver ya autenticado.
        logger: logger compartido.
        fecha: fecha en formato dd-mm-yyyy. Si es None, pregunta al usuario.

    Returns:
        Lista de PacienteIniciado. Vacía si no hay fichas iniciadas.

    Raises:
        RuntimeError: si la sesión de Rayen es inválida.
        ValueError: si el formato de fecha es inválido.
        selenium.common.exceptions.TimeoutException: si la UI no responde.
    """
    if not ensure_session_alive(driver, logger):
        raise RuntimeError("La sesión de Rayen es inválida. Reautenticar.")

    logger.info(f"[pancho] Listando fichas 'Iniciado' para fecha={fecha or 'hoy'}")
    select_date(driver, logger, fecha_str=fecha)
    sort_by_estado(driver, logger)
    rows = get_pacientes_iniciados(driver, logger)

    pacientes: list[PacienteIniciado] = []
    for row in rows:
        try:
            datos = extraer_datos_fila(row)
        except ValueError as e:
            logger.warning(f"[pancho] Fila saltada por error: {e}")
            continue
        pacientes.append(
            PacienteIniciado(
                hora=datos["hora"],
                estado=datos["estado"],
                nombre=datos["nombre"],
                tipo_cupo=datos["tipo_cupo"],
                llegada=datos["llegada"],
                llamada=datos["llamada"],
                razon=datos["razon"],
                tipo_atencion_raw=datos["tipo_atencion"],
                tipo_atencion=sanitizar_tipo(datos["tipo_atencion"]),
                adjunto=datos["adjunto"],
            )
        )
    logger.info(f"[pancho] {len(pacientes)} fichas 'Iniciado' recuperadas")
    return pacientes
