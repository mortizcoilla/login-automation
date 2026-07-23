"""Skill: enviar una ficha a Rayen.

STUB parcial — la validación del token (delegada a `queue_store`) ya
está implementada. La lógica de submit real (qué botones clickear,
qué URL llamar, qué payload enviar) queda pendiente hasta que se
descubra el flujo en Rayen.

La validación del token es la pieza CRÍTICA de seguridad. Aunque
el submit real no esté implementado, la skill YA rechaza cualquier
llamada que no venga con un token válido persistido en `queue_store`.

El token se genera, persiste y valida en `queue_store` (no acá). Esto
es intencional: la DB es la fuente de verdad para audit + TTL + uso.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from selenium.webdriver.remote.webdriver import WebDriver

from src.queue_store import TokenInvalidoError, validar_y_consumir_token


@dataclass
class ResultadoEnvio:
    """Resultado de un envío de ficha a Rayen."""

    ficha_id: int
    timestamp: str
    hash_contenido: str
    estado: str  # "ENVIADO" cuando esté implementado


_DB_PATH_DEFAULT = "data/queue.db"


def _get_db_path() -> str:
    """Permite override por env var para tests; default apunta a la DB real."""
    return os.environ.get("LOGIN_AUTOMATION_DB", _DB_PATH_DEFAULT)


def enviar_ficha(
    driver: WebDriver,
    ficha_id: int,
    paciente_id: str,
    contenido: str,
    token: int,
    logger: logging.Logger,
) -> ResultadoEnvio:
    """Envía una ficha a Rayen con verificación de token de aprobación.

    Args:
        driver: WebDriver ya autenticado.
        ficha_id: ID de la ficha.
        paciente_id: ID del paciente.
        contenido: contenido final de la ficha (post-aprobación).
        token: ID del token generado por Pilita tras la doble confirmación.
        logger: logger compartido.

    Returns:
        ResultadoEnvio con timestamp y hash para auditoría.

    Raises:
        TokenInvalidoError: si el token no es válido, está expirado,
            ya fue usado, o no corresponde a esta ficha + contenido.
        NotImplementedError: la lógica de submit real no está implementada.
    """
    # Validar contra la DB. Si pasa, marca el token como usado.
    validar_y_consumir_token(
        db_path=_get_db_path(),
        token_id=int(token),
        ficha_id=int(ficha_id),
        contenido=contenido,
    )

    logger.info(
        f"[pancho] Token #{token} válido. Procediendo con envío de ficha={ficha_id}"
    )
    # TODO: implementar la lógica real de submit a Rayen
    raise NotImplementedError(
        "enviar_ficha: el submit real a Rayen no está implementado. "
        "Pasos: (1) descubrir el flujo de submit en Rayen "
        "(clicks, URL, payload), (2) implementar aquí usando el WebDriver "
        "o, preferentemente, el endpoint REST si existe. "
        "Mientras tanto, el principio de validación (token) YA está activo."
    )
