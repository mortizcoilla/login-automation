"""Configuration for the Telegram bot (Rubicita).

Carga variables de entorno via python-dotenv. Token y user IDs son obligatorios.

Variables (en .env):
    TELEGRAM_BOT_TOKEN_RUBICITA     Token del bot (de @BotFather). Obligatorio.
    TELEGRAM_ALLOWED_USER_IDS       IDs de Telegram separados por coma. Obligatorio.
    TELEGRAM_POLLING_INTERVAL       Segundos entre polls (default 1.0). Opcional.
    TELEGRAM_LOG_LEVEL              Nivel de logging (default INFO). Opcional.
    TELEGRAM_NOTAS_DIR              Override del dir de notas clinicas (solo tests).
    TELEGRAM_DESTINO_DIR            Override del dir destino (solo tests).

Para obtener el user_id de Yadira: hablarle al bot @userinfobot o agregar
un logueo temporal que imprima update.effective_user.id en el primer
mensaje que llegue.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class ConfigurationError(ValueError):
    """Configuracion faltante o invalida (token vacio, sin usuarios, etc.)."""


@dataclass(frozen=True)
class BotConfig:
    """Configuracion validada del bot, lista para construir la Application.

    Atributos:
        token: token del bot (no loggear).
        allowed_user_ids: tupla inmutable de IDs autorizados.
        polling_interval: segundos entre polls del long-polling.
        log_level: nivel de logging (uppercase, pre-validado).
        notas_dir_path: ruta absoluta al dir de notas clinicas, o None
            para usar el default del kernel.
        destino_dir_path: ruta absoluta al dir destino de examenes, o None
            para usar el default del kernel.
    """

    token: str
    allowed_user_ids: frozenset[int]
    polling_interval: float
    log_level: str
    notas_dir_path: str | None
    destino_dir_path: str | None

    @classmethod
    def from_env(cls) -> BotConfig:
        """Lee .env (silenciosamente si no existe) y construye BotConfig.

        Raises:
            ConfigurationError: si falta TELEGRAM_BOT_TOKEN_RUBICITA,
                TELEGRAM_ALLOWED_USER_IDS, o si los IDs no son enteros.
        """
        load_dotenv()

        token = os.getenv("TELEGRAM_BOT_TOKEN_RUBICITA", "").strip()
        if not token:
            raise ConfigurationError(
                "TELEGRAM_BOT_TOKEN_RUBICITA no esta definida. "
                "Copia .env.example a .env y agrega el token de @BotFather."
            )

        raw_ids = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").strip()
        if not raw_ids:
            raise ConfigurationError(
                "TELEGRAM_ALLOWED_USER_IDS no esta definida. "
                "Lista separada por comas con los IDs de Telegram de Yadira "
                "(y operador si aplica). Para obtener el ID: "
                "escribirle a @userinfobot."
            )

        try:
            parsed = [int(x.strip()) for x in raw_ids.split(",") if x.strip()]
        except ValueError as exc:
            raise ConfigurationError(
                f"TELEGRAM_ALLOWED_USER_IDS contiene valores no enteros: {exc}"
            ) from None

        if not parsed:
            raise ConfigurationError("TELEGRAM_ALLOWED_USER_IDS no contiene IDs validos (enteros).")

        try:
            polling_interval = float(os.getenv("TELEGRAM_POLLING_INTERVAL", "1.0"))
        except ValueError as exc:
            raise ConfigurationError(f"TELEGRAM_POLLING_INTERVAL invalido: {exc}") from None
        if polling_interval <= 0:
            raise ConfigurationError(
                f"TELEGRAM_POLLING_INTERVAL debe ser > 0, recibio {polling_interval}"
            )

        log_level = os.getenv("TELEGRAM_LOG_LEVEL", "INFO").upper()
        if log_level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            raise ConfigurationError(
                f"TELEGRAM_LOG_LEVEL invalido: {log_level!r}. "
                f"Esperado: DEBUG/INFO/WARNING/ERROR/CRITICAL."
            )

        notas_dir = os.getenv("TELEGRAM_NOTAS_DIR", "").strip() or None
        destino_dir = os.getenv("TELEGRAM_DESTINO_DIR", "").strip() or None

        return cls(
            token=token,
            allowed_user_ids=frozenset(parsed),
            polling_interval=polling_interval,
            log_level=log_level,
            notas_dir_path=notas_dir,
            destino_dir_path=destino_dir,
        )
