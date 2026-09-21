"""Auth middleware: solo usuarios whitelist pueden usar el bot.

Por ahora la whitelist es fija (Yadira + operador). Esto es deliberadamente
simple: el bot vive detras de NAT (polling local), no es superficie de ataque.
Si en el futuro hay que rotar IDs seguido, mover a SQLite via queue_store.

Comportamiento:
- Si update.effective_user no existe (canal raro, ej. canal sin user): drop
  silencioso, log WARNING.
- Si user.id no esta en allowed_ids: drop silencioso. NO respondemos al
  usuario no autorizado (evita info leak: que sepan que existe el bot).
- Si autorizado: delega al handler original.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def authorized_only(
    allowed_ids: frozenset[int],
) -> Callable[
    [Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]],
    Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]],
]:
    """Decorador: rechaza updates de usuarios no autorizados.

    Args:
        allowed_ids: frozenset de Telegram user IDs que pueden usar el bot.

    Returns:
        Decorador que envuelve un handler PTB. El handler resultante drop
        silenciosamente updates de usuarios no autorizados.

    Ejemplo:
        @authorized_only(allowed_ids)
        async def mi_handler(update, context): ...
    """

    def decorator(
        func: Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]],
    ) -> Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]:
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            user = update.effective_user
            if user is None:
                logger.warning("Update sin effective_user; rechazado.")
                return
            if user.id not in allowed_ids:
                logger.warning(
                    "Acceso rechazado: user_id=%s username=%r first_name=%r",
                    user.id,
                    user.username,
                    user.first_name,
                )
                # No respondemos para evitar info leak (no dar senal de
                # que el bot existe).
                return
            return await func(update, context)

        return wrapper

    return decorator
